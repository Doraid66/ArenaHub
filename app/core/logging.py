"""Structured (JSON) logs, and a correlation ID for every request.

Each request gets an ID (taken from the caller's X-Request-ID header if it is safe,
otherwise generated). Every log line written while handling that request includes
the ID, and the response sends it back in the X-Request-ID header.
"""

import contextvars  # Per-request storage that is safe with concurrency.
import json  # Write each log line as JSON.
import logging  # Python's standard logging.
import re  # Check that request IDs look safe.
import time  # Measure request duration.
import uuid  # Generate request IDs.
from datetime import datetime, timezone  # Timestamp each log line in UTC.

from fastapi import Request  # The incoming request.
from fastapi.responses import JSONResponse  # Build the 500 response by hand.

from app.core.errors import error_body  # Shared error format.

# Holds the current request's ID. A ContextVar keeps a separate value for each
# request, even when many requests are handled at the same time.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")  # "-" outside any request.

# Only accept short, simple IDs from callers, so nobody can inject junk into our logs.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")  # 1-64 letters, digits, dot, underscore, or dash.

logger = logging.getLogger("arenahub.request")  # Logger for the per-request summary line.


class JsonFormatter(logging.Formatter):  # Formats log records as JSON.
    """Turn each log record into one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:  # Called for every log record.
        entry = {  # The fields every line has.
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),  # When it happened, in UTC.
            "level": record.levelname,  # INFO, WARNING, ...
            "logger": record.name,  # Which logger wrote it.
            "message": record.getMessage(),  # The log text.
            "request_id": request_id_var.get(),  # Ties the line to its request.
        }  # Finish the base fields.
        # Extra structured fields, passed as: logger.info("...", extra={"fields": {...}})
        fields = getattr(record, "fields", None)  # Optional extra fields.
        if isinstance(fields, dict):  # Only accept a dictionary.
            entry.update(fields)  # Merge them into the line.
        if record.exc_info:  # An exception was logged.
            entry["exception"] = self.formatException(record.exc_info)  # Include the traceback text.
        return json.dumps(entry, default=str)  # One JSON line; unknown types become strings.


def setup_logging(level: str = "INFO") -> None:  # Configure logging once at startup.
    """Send all logs to the console as JSON. Called once at startup."""
    handler = logging.StreamHandler()  # Write to the console.
    handler.setFormatter(JsonFormatter())  # Use the JSON format.
    root = logging.getLogger()  # The top-level logger.
    root.handlers = [handler]  # Replace any existing handlers.
    root.setLevel(level.upper())  # Apply the chosen level.


async def request_context_middleware(request: Request, call_next):  # Wraps every request.
    """Runs around every request: assign the ID, time the request, log one summary line."""
    incoming = request.headers.get("X-Request-ID", "")  # ID sent by the caller, if any.
    request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex  # Use it only if safe.
    token = request_id_var.set(request_id)  # Store it for this request's logs.
    start = time.perf_counter()  # Start the timer.
    try:  # Always reset the ID afterwards.
        try:  # Catch errors from the rest of the app.
            response = await call_next(request)  # Run the actual route.
        except Exception:  # Something unexpected failed.
            # Last line of defence: log the details, return the generic error.
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)  # Log the traceback.
            response = JSONResponse(  # Build a generic 500.
                status_code=500,  # Internal Server Error.
                content=error_body("internal_error", "An unexpected error occurred"),  # No internal details.
            )  # Finish the 500 response.
        duration_ms = round((time.perf_counter() - start) * 1000, 1)  # Elapsed time in milliseconds.
        response.headers["X-Request-ID"] = request_id  # Send the ID back to the caller.
        # Never log headers, bodies or query strings: they can contain tokens or passwords.
        logger.info(  # One summary line per request.
            "request completed",  # Log message.
            extra={"fields": {  # Structured extras.
                "method": request.method,  # GET, POST, ...
                "path": request.url.path,  # URL path without the query string.
                "status": response.status_code,  # HTTP status sent.
                "duration_ms": duration_ms,  # How long it took.
            }},  # Finish the extras.
        )  # Finish the log call.
        return response  # Send the response on.
    finally:  # Runs even if something above failed.
        request_id_var.reset(token)  # Clear this request's ID.
