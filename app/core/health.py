"""Health checks used by Docker and by humans.

/health/live  - is the API process running? (never touches the database)
/health/ready - can the API actually serve requests? (checks the database)
Both are public and reveal no internal details.
"""

import logging  # Log failed readiness checks.

from fastapi import APIRouter, Depends  # Router and dependency injection.
from fastapi.responses import JSONResponse  # Build the 503 response by hand.
from pydantic import BaseModel  # Describe the response shape.
from sqlalchemy import text  # Run a raw SQL statement.
from sqlalchemy.exc import SQLAlchemyError  # Any database failure.
from sqlalchemy.orm import Session  # The request's database session.

from app.core.database import get_db  # Gives each request its own session.
from app.core.errors import error_body, error_responses  # Shared error format and OpenAPI helper.

logger = logging.getLogger("arenahub.health")  # Logger for this module.

router = APIRouter(prefix="/health", tags=["health"])  # All routes here start with /health.


class HealthStatus(BaseModel):  # The health response.
    status: str  # "ok" or "ready".


@router.get("/live", response_model=HealthStatus)  # GET /health/live.
def live() -> HealthStatus:  # Is the process running?
    return HealthStatus(status="ok")  # No database access at all.


@router.get(  # GET /health/ready.
    "/ready",  # URL path.
    response_model=HealthStatus,  # Shape of the JSON answer.
    responses=error_responses(503),  # Documents the "not ready" answer.
)  # Finish the route declaration.
def ready(db: Session = Depends(get_db)):  # Can the app reach the database?
    try:  # The query may fail.
        db.execute(text("SELECT 1"))  # Cheapest possible database round trip.
    except SQLAlchemyError as exc:  # The database is unreachable or broken.
        # Log only the error type: the full message can include connection details.
        logger.warning("Readiness check failed: %s", type(exc).__name__)  # Record the failure safely.
        return JSONResponse(  # Answer 503 in the shared error format.
            status_code=503,  # Service Unavailable.
            content=error_body("service_unavailable", "Service is not ready"),  # No internal details.
        )  # Finish the 503 response.
    return HealthStatus(status="ready")  # The database answered.
