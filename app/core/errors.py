"""One error format for the whole API: {"error": {"code": "...", "message": "..."}}.

Services raise the typed errors below (e.g. `raise SlotUnavailableError()`);
the handlers registered in main.py turn them into JSON responses.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("arenahub.errors")


def error_body(code: str, message: str) -> dict:
    """Build the shared error envelope."""
    return {"error": {"code": code, "message": message}}


# ---------- Typed errors that services raise ----------

class AppError(Exception):
    """Base class for every expected API error."""

    status_code: int = 400
    code: str = "bad_request"
    message: str = "Bad request"
    headers: dict[str, str] | None = None

    def __init__(self, message: str | None = None) -> None:
        # Use the custom message if one is given, otherwise the class default.
        if message is not None:
            self.message = message
        super().__init__(self.message)


class UnauthenticatedError(AppError):
    status_code = 401
    code = "unauthenticated"
    message = "Authentication required"
    headers = {"WWW-Authenticate": "Bearer"}


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "You are not allowed to perform this action"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found"


class SlotUnavailableError(AppError):
    status_code = 409
    code = "slot_unavailable"
    message = "Requested field space is unavailable"


class IdempotencyConflictError(AppError):
    status_code = 409
    code = "idempotency_conflict"
    message = "This Idempotency-Key was already used with a different request"


class InvalidInputError(AppError):
    status_code = 422
    code = "invalid_input"
    message = "The request is invalid"


# ---------- Handlers that turn errors into responses ----------

# Error codes for FastAPI's own errors (unknown URL, wrong method, ...).
_HTTP_STATUS_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "invalid_input",
    429: "rate_limited",
    503: "service_unavailable",
}


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message),
        headers=exc.headers,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message),
        headers=getattr(exc, "headers", None),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Keep only the field location and the reason. FastAPI's raw errors also contain
    # the submitted value, which could be a password, so we never echo it back.
    details = [
        {"field": ".".join(str(part) for part in err.get("loc", [])), "reason": err.get("msg", "")}
        for err in exc.errors()
    ]
    body = error_body("invalid_input", "The request is invalid")
    body["error"]["details"] = details
    return JSONResponse(status_code=422, content=body)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Full details go to the server log only; the caller never sees a traceback.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content=error_body("internal_error", "An unexpected error occurred"))


def register_error_handlers(app: FastAPI) -> None:
    """Called once in main.py."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)