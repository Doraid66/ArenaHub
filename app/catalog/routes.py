"""HTTP routes for the catalog. Thin: read the request, call the service, return the result."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.catalog.schemas import AvailabilityOut, FieldListOut
from app.catalog.service import AvailabilityChecker, CatalogService
from app.core.database import get_db
from app.core.errors import ServiceUnavailableError, error_responses
from app.core.principal import Principal, get_current_principal

router = APIRouter(tags=["catalog"])


# ---------- Dependencies ----------

def get_availability_checker(db: Session = Depends(get_db)) -> AvailabilityChecker:
    """The shared reservation engine (Person 1) answers availability questions.

    The import happens here, at request time, because the engine lives on Person 1's
    branch until integration. Tests replace this dependency with a fake.
    """
    try:
        from app.reservations.service import ReservationService
    except ModuleNotFoundError as exc:
        if exc.name in ("app.reservations", "app.reservations.service"):
            raise ServiceUnavailableError("Availability is not available yet") from None
        raise  # the engine exists but has a broken import: show the real error
    return ReservationService(db)


def get_catalog_service(db: Session = Depends(get_db)) -> CatalogService:
    return CatalogService(db)


def get_catalog_service_with_availability(
    db: Session = Depends(get_db),
    availability: AvailabilityChecker = Depends(get_availability_checker),
) -> CatalogService:
    return CatalogService(db, availability)


# ---------- Routes ----------

@router.get(
    "/fields",
    response_model=FieldListOut,
    summary="List all fields",
    responses=error_responses(401),
)
def list_fields(
    principal: Principal = Depends(get_current_principal),  # login required
    service: CatalogService = Depends(get_catalog_service),
) -> FieldListOut:
    return service.list_fields()


@router.get(
    "/fields/{field_id}/availability",
    response_model=AvailabilityOut,
    summary="Is this field free for the whole interval?",
    responses=error_responses(401, 404, 422, 503),
)
def check_availability(
    field_id: uuid.UUID,
    start: datetime = Query(description="Start, with a timezone offset, e.g. 2026-11-15T20:00:00-05:00"),
    end: datetime = Query(description="End, with a timezone offset; must be after start"),
    principal: Principal = Depends(get_current_principal),  # login required
    service: CatalogService = Depends(get_catalog_service_with_availability),
) -> AvailabilityOut:
    # Advisory only: the booking endpoint makes the final decision.
    return service.check_availability(field_id, start, end)