"""Structured (JSON) logs, and a correlation ID for every request.

Each request gets an ID (taken from the caller's X-Request-ID header if it is safe,
otherwise generated). Every log line written while handling that request includes
the ID, and the response sends it back in the X-Request-ID header.
"""

import contextvars
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import error_body

# Holds the current request's ID. A ContextVar keeps a separate value for each
# request, even when many requests are handled at the same time.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Only accept short, simple IDs from callers, so nobody can inject junk into our logs.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

logger = logging.getLogger("arenahub.request")


class JsonFormatter(logging.Formatter):
    """Turn each log record into one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        # Extra structured fields, passed as: logger.info("...", extra={"fields": {...}})
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            entry.update(fields)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Send all logs to the console as JSON. Called once at startup."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


async def request_context_middleware(request: Request, call_next):
    """Runs around every request: assign the ID, time the request, log one summary line."""
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            # Last line of defence: log the details, return the generic error.
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            response = JSONResponse(
                status_code=500,
                content=error_body("internal_error", "An unexpected error occurred"),
            )
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        # Never log headers, bodies or query strings: they can contain tokens or passwords.
        logger.info(
            "request completed",
            extra={"fields": {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            }},
        )
        return response
    finally:
        request_id_var.reset(token)