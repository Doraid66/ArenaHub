"""One error format for the whole API: {"error": {"code": "...", "message": "..."}}.

Services raise the typed errors below (e.g. `raise SlotUnavailableError()`);
the handlers registered in main.py turn them into JSON responses.
"""

import logging  # Log unexpected errors.

from fastapi import FastAPI, Request  # The app object and the incoming request.
from fastapi.exceptions import RequestValidationError  # FastAPI's input-validation error.
from fastapi.responses import JSONResponse  # Build JSON error responses.
from pydantic import BaseModel  # Describe the error shape for OpenAPI.
from starlette.exceptions import HTTPException as StarletteHTTPException  # Errors like unknown URL or wrong method.

logger = logging.getLogger("arenahub.errors")  # Logger for this module.


def error_body(code: str, message: str) -> dict:  # Make the standard error JSON.
    """Build the shared error envelope."""
    return {"error": {"code": code, "message": message}}  # Every error looks like this.


# ---------- Error shape for the OpenAPI contract ----------

class ValidationIssue(BaseModel):  # One problem found in the request.
    field: str  # Where the problem is, e.g. "body.start".
    reason: str  # What is wrong.


class ErrorDetail(BaseModel):  # The inside of the error envelope.
    code: str  # Stable machine-readable code.
    message: str  # Human-readable message.
    details: list[ValidationIssue] | None = None  # Only on 422 validation errors.


class ErrorResponse(BaseModel):  # The full error response.
    error: ErrorDetail  # The envelope's only key.


# Fixed descriptions, so the contract does not depend on the Python version.
# (Python 3.13 renamed 422 from "Unprocessable Entity" to "Unprocessable Content".)
_ERROR_DESCRIPTIONS = {  # Status code to description text.
    400: "Bad Request",  # Request could not be read.
    401: "Unauthorized",  # Missing or invalid login.
    403: "Forbidden",  # Logged in but not allowed.
    404: "Not Found",  # Resource does not exist.
    409: "Conflict",  # Clashes with current state.
    422: "Unprocessable Entity",  # Input failed validation.
    500: "Internal Server Error",  # Unexpected failure.
    503: "Service Unavailable",  # A dependency is not ready.
}  # Finish the descriptions.


def error_responses(*status_codes: int) -> dict:  # Document error responses on a route.
    """Document error responses on a route, e.g. responses=error_responses(401, 404)."""
    return {  # Mapping in the shape FastAPI expects.
        code: {"model": ErrorResponse, "description": _ERROR_DESCRIPTIONS.get(code, "Error")}  # Same model, own description.
        for code in status_codes  # One entry per requested code.
    }  # Finish the mapping.


_ERROR_REF = {"$ref": "#/components/schemas/ErrorResponse"}  # OpenAPI pointer to the error schema.
_FASTAPI_VALIDATION_REF = "#/components/schemas/HTTPValidationError"  # FastAPI's own 422 schema, which we replace.


def _error_content() -> dict:  # JSON content block pointing at ErrorResponse.
    return {"application/json": {"schema": dict(_ERROR_REF)}}  # Fresh copy each time.


def make_contract_match_error_format(app: FastAPI) -> None:  # Patch the published OpenAPI document.
    """Make the published contract describe the errors the API really returns.

    Applied to every route automatically, so nobody has to remember it:
    - 422: FastAPI documents its own {"detail": [...]} shape, but our handler returns
      {"error": {...}}. Every 422 is re-pointed to ErrorResponse.
    - 401: every route that requires a login token is documented as returning 401.
    - 400: every route with a request body is documented as returning 400 (FastAPI
      answers 400 when the body can't be read at all, e.g. broken bytes).
    Called once in main.py.
    """
    generate = app.openapi  # Keep FastAPI's original generator.

    def openapi() -> dict:  # Replacement generator.
        if app.openapi_schema is not None:  # Already built once.
            return app.openapi_schema  # Reuse the cached document.
        schema = generate()  # Let FastAPI build the normal document.
        schemas = schema.setdefault("components", {}).setdefault("schemas", {})  # The shared schemas section.

        # Make sure ErrorResponse (and the models it uses) are in the contract.
        error_schema = ErrorResponse.model_json_schema(ref_template="#/components/schemas/{model}")  # Schema of our error shape.
        for name, definition in error_schema.pop("$defs", {}).items():  # Nested models used by the error shape.
            schemas.setdefault(name, definition)  # Add each one if missing.
        schemas.setdefault("ErrorResponse", error_schema)  # Add the error shape itself.

        for operations in schema.get("paths", {}).values():  # Every URL path.
            for operation in operations.values():  # Every method on that path.
                responses = operation.setdefault("responses", {})  # The documented responses.
                invalid = responses.get("422")  # The validation-error response, if any.
                if invalid:  # This route documents a 422.
                    current = invalid.get("content", {}).get("application/json", {}).get("schema", {})  # Its current schema.
                    if current.get("$ref") == _FASTAPI_VALIDATION_REF:  # Still FastAPI's default shape.
                        invalid["content"] = _error_content()  # Point it at our error shape.
                        invalid["description"] = "Invalid input"  # Friendlier description.
                if "requestBody" in operation and "400" not in responses:  # Has a body but no 400 documented.
                    responses["400"] = {"description": "Request body could not be read",  # Add the 400 response.
                                        "content": _error_content()}  # Using our error shape.
                if operation.get("security") and "401" not in responses:  # Needs login but no 401 documented.
                    responses["401"] = {"description": "Missing, invalid or expired token",  # Add the 401 response.
                                        "content": _error_content()}  # Using our error shape.

        # FastAPI's validation schemas are no longer used anywhere.
        if _FASTAPI_VALIDATION_REF not in str(schema["paths"]):  # Nothing refers to it any more.
            schemas.pop("HTTPValidationError", None)  # Remove the unused schema.
            schemas.pop("ValidationError", None)  # Remove the unused schema.
        return schema  # The patched document.

    app.openapi = openapi  # Install the patched generator.


# ---------- Typed errors that services raise ----------

class AppError(Exception):  # Parent of every expected API error.
    """Base class for every expected API error."""

    status_code: int = 400  # HTTP status to send.
    code: str = "bad_request"  # Stable machine-readable code.
    message: str = "Bad request"  # Default human-readable message.
    headers: dict[str, str] | None = None  # Extra response headers, if any.

    def __init__(self, message: str | None = None) -> None:  # Optionally override the message.
        # Use the custom message if one is given, otherwise the class default.
        if message is not None:  # A custom message was given.
            self.message = message  # Store it on this instance.
        super().__init__(self.message)  # Also set the normal exception text.


class UnauthenticatedError(AppError):  # Not logged in, or the token is bad.
    status_code = 401  # HTTP Unauthorized.
    code = "unauthenticated"  # Machine-readable code.
    message = "Authentication required"  # Default message.
    headers = {"WWW-Authenticate": "Bearer"}  # Tells clients to send a bearer token.


class ForbiddenError(AppError):  # Logged in but not allowed.
    status_code = 403  # HTTP Forbidden.
    code = "forbidden"  # Machine-readable code.
    message = "You are not allowed to perform this action"  # Default message.


class NotFoundError(AppError):  # The resource does not exist.
    status_code = 404  # HTTP Not Found.
    code = "not_found"  # Machine-readable code.
    message = "Resource not found"  # Default message.


class SlotUnavailableError(AppError):  # The requested time is already taken.
    status_code = 409  # HTTP Conflict.
    code = "slot_unavailable"  # Machine-readable code.
    message = "Requested field space is unavailable"  # Default message.


class IdempotencyConflictError(AppError):  # A retry key was reused for a different request.
    status_code = 409  # HTTP Conflict.
    code = "idempotency_conflict"  # Machine-readable code.
    message = "This Idempotency-Key was already used with a different request"  # Default message.


class ServiceUnavailableError(AppError):  # A needed part is not ready.
    status_code = 503  # HTTP Service Unavailable.
    code = "service_unavailable"  # Machine-readable code.
    message = "Service temporarily unavailable"  # Default message.


class InvalidInputError(AppError):  # The request data is wrong.
    status_code = 422  # HTTP Unprocessable Entity.
    code = "invalid_input"  # Machine-readable code.
    message = "The request is invalid"  # Default message.


# ---------- Handlers that turn errors into responses ----------

# Error codes for FastAPI's own errors (unknown URL, wrong method, ...).
_HTTP_STATUS_CODES = {  # Status code to our error code.
    400: "bad_request",  # Request could not be read.
    401: "unauthenticated",  # Missing or invalid login.
    403: "forbidden",  # Logged in but not allowed.
    404: "not_found",  # Unknown URL or resource.
    405: "method_not_allowed",  # Wrong HTTP method for this URL.
    409: "conflict",  # Clashes with current state.
    422: "invalid_input",  # Input failed validation.
    429: "rate_limited",  # Too many requests.
    503: "service_unavailable",  # A dependency is not ready.
}  # Finish the code table.


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:  # Turn our own errors into JSON.
    return JSONResponse(  # Build the response.
        status_code=exc.status_code,  # Status chosen by the error class.
        content=error_body(exc.code, exc.message),  # Standard error JSON.
        headers=exc.headers,  # Extra headers such as WWW-Authenticate.
    )  # Finish the response.


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:  # Reformat framework errors.
    code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")  # Pick our code, or a generic one.
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"  # Only show plain-text details.
    return JSONResponse(  # Build the response.
        status_code=exc.status_code,  # Keep the original status.
        content=error_body(code, message),  # Standard error JSON.
        headers=getattr(exc, "headers", None),  # Keep headers such as Allow.
    )  # Finish the response.


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:  # Reformat input-validation errors.
    # Keep only the field location and the reason. FastAPI's raw errors also contain
    # the submitted value, which could be a password, so we never echo it back.
    details = [  # One entry per problem.
        {"field": ".".join(str(part) for part in err.get("loc", [])), "reason": err.get("msg", "")}  # Location and reason only.
        for err in exc.errors()  # Each problem FastAPI found.
    ]  # Finish the list.
    body = error_body("invalid_input", "The request is invalid")  # Start from the standard error.
    body["error"]["details"] = details  # Attach the per-field problems.
    return JSONResponse(status_code=422, content=body)  # Send a 422 with the details.


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:  # Catch anything unexpected.
    # Full details go to the server log only; the caller never sees a traceback.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)  # Log the traceback.
    return JSONResponse(status_code=500, content=error_body("internal_error", "An unexpected error occurred"))  # Generic 500 for the caller.


def register_error_handlers(app: FastAPI) -> None:  # Connect all handlers to the app.
    """Called once in main.py."""
    app.add_exception_handler(AppError, app_error_handler)  # Our own errors.
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # Unknown URL, wrong method, etc.
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # Bad request data.
    app.add_exception_handler(Exception, unhandled_error_handler)  # Everything else.
