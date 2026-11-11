"""One error format for the whole API: {"error": {"code": "...", "message": "..."}}.

Services raise the typed errors below (e.g. `raise SlotUnavailableError()`);
the handlers registered in main.py turn them into JSON responses.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("arenahub.errors")


def error_body(code: str, message: str) -> dict:
    """Build the shared error envelope."""
    return {"error": {"code": code, "message": message}}


# ---------- Error shape for the OpenAPI contract ----------

class ValidationIssue(BaseModel):
    field: str
    reason: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[ValidationIssue] | None = None  # only on 422 validation errors


class ErrorResponse(BaseModel):
    error: ErrorDetail


# Fixed descriptions, so the contract does not depend on the Python version.
# (Python 3.13 renamed 422 from "Unprocessable Entity" to "Unprocessable Content".)
_ERROR_DESCRIPTIONS = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def error_responses(*status_codes: int) -> dict:
    """Document error responses on a route, e.g. responses=error_responses(401, 404)."""
    return {
        code: {"model": ErrorResponse, "description": _ERROR_DESCRIPTIONS.get(code, "Error")}
        for code in status_codes
    }


_ERROR_REF = {"$ref": "#/components/schemas/ErrorResponse"}
_FASTAPI_VALIDATION_REF = "#/components/schemas/HTTPValidationError"


def _error_content() -> dict:
    return {"application/json": {"schema": dict(_ERROR_REF)}}


def make_contract_match_error_format(app: FastAPI) -> None:
    """Make the published contract describe the errors the API really returns.

    Applied to every route automatically, so nobody has to remember it:
    - 422: FastAPI documents its own {"detail": [...]} shape, but our handler returns
      {"error": {...}}. Every 422 is re-pointed to ErrorResponse.
    - 401: every route that requires a login token is documented as returning 401.
    - 400: every route with a request body is documented as returning 400 (FastAPI
      answers 400 when the body can't be read at all, e.g. broken bytes).
    Called once in main.py.
    """
    generate = app.openapi

    def openapi() -> dict:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = generate()
        schemas = schema.setdefault("components", {}).setdefault("schemas", {})

        # Make sure ErrorResponse (and the models it uses) are in the contract.
        error_schema = ErrorResponse.model_json_schema(ref_template="#/components/schemas/{model}")
        for name, definition in error_schema.pop("$defs", {}).items():
            schemas.setdefault(name, definition)
        schemas.setdefault("ErrorResponse", error_schema)

        for operations in schema.get("paths", {}).values():
            for operation in operations.values():
                responses = operation.setdefault("responses", {})
                invalid = responses.get("422")
                if invalid:
                    current = invalid.get("content", {}).get("application/json", {}).get("schema", {})
                    if current.get("$ref") == _FASTAPI_VALIDATION_REF:
                        invalid["content"] = _error_content()
                        invalid["description"] = "Invalid input"
                if "requestBody" in operation and "400" not in responses:
                    responses["400"] = {"description": "Request body could not be read",
                                        "content": _error_content()}
                if operation.get("security") and "401" not in responses:
                    responses["401"] = {"description": "Missing, invalid or expired token",
                                        "content": _error_content()}

        # FastAPI's validation schemas are no longer used anywhere.
        if _FASTAPI_VALIDATION_REF not in str(schema["paths"]):
            schemas.pop("HTTPValidationError", None)
            schemas.pop("ValidationError", None)
        return schema

    app.openapi = openapi


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


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "Service temporarily unavailable"


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