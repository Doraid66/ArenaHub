"""Health checks used by Docker and by humans.

/health/live  - is the API process running? (never touches the database)
/health/ready - can the API actually serve requests? (checks the database)
Both are public and reveal no internal details.
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import error_body, error_responses

logger = logging.getLogger("arenahub.health")

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    status: str


@router.get("/live", response_model=HealthStatus)
def live() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get(
    "/ready",
    response_model=HealthStatus,
    responses=error_responses(503),
)
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # Log only the error type: the full message can include connection details.
        logger.warning("Readiness check failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content=error_body("service_unavailable", "Service is not ready"),
        )
    return HealthStatus(status="ready")