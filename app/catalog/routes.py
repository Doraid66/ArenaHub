"""HTTP routes for the catalog. Thin: read the request, call the service, return the result."""

import uuid  # Path IDs are UUIDs.
from typing import Annotated  # Attach query-parameter details to a type.

from fastapi import APIRouter, Depends, Query  # Router, dependency injection, and query parameters.
from sqlalchemy.orm import Session  # The request's database session.

from app.catalog.schemas import AvailabilityOut, FieldListOut  # Response shapes.
from app.catalog.service import AvailabilityChecker, CatalogService  # The catalog rules and the checker interface.
from app.core.database import get_db  # Gives each request its own session.
from app.core.errors import ServiceUnavailableError, error_responses  # Shared errors and OpenAPI helper.
from app.core.principal import Principal, get_current_principal  # The verified caller.
from app.core.timestamps import UtcTimestamp  # Strict timestamp type with a required offset.

router = APIRouter(tags=["catalog"])  # Group these routes under "catalog" in the docs.


# ---------- Dependencies ----------

def get_availability_checker(db: Session = Depends(get_db)) -> AvailabilityChecker:  # Provide the engine that answers availability.
    """The shared reservation engine (Person 1) answers availability questions.

    The import happens here, at request time, because the engine lives on Person 1's
    branch until integration. Tests replace this dependency with a fake.
    """
    try:  # The engine module may not exist yet.
        from app.reservations.service import ReservationService  # Import late, only when needed.
    except ModuleNotFoundError as exc:  # The import failed.
        if exc.name in ("app.reservations", "app.reservations.service"):  # The engine itself is missing.
            raise ServiceUnavailableError("Availability is not available yet") from None  # Answer 503 instead of crashing.
        raise  # The engine exists but has a broken import: show the real error.
    return ReservationService(db)  # Real engine on this request's session.


def get_catalog_service(db: Session = Depends(get_db)) -> CatalogService:  # Catalog service without availability.
    return CatalogService(db)  # Enough for listing fields.


def get_catalog_service_with_availability(  # Catalog service that can also check availability.
    db: Session = Depends(get_db),  # The request's session.
    availability: AvailabilityChecker = Depends(get_availability_checker),  # The engine that answers.
) -> CatalogService:  # The service to use in the route.
    return CatalogService(db, availability)  # Pass the engine in.


# ---------- Routes ----------

@router.get(  # GET /fields.
    "/fields",  # URL path.
    response_model=FieldListOut,  # Shape of the JSON answer.
    summary="List all fields",  # Short title in the docs.
    responses=error_responses(401),  # Documents the login error.
)  # Finish the route declaration.
def list_fields(  # List every bookable field.
    principal: Principal = Depends(get_current_principal),  # Login required.
    service: CatalogService = Depends(get_catalog_service),  # Service built for this request.
) -> FieldListOut:  # Return the list shape.
    return service.list_fields()  # The service does the work.


@router.get(  # GET /fields/{field_id}/availability.
    "/fields/{field_id}/availability",  # URL path with the field ID.
    response_model=AvailabilityOut,  # Shape of the JSON answer.
    summary="Is this field free for the whole interval?",  # Short title in the docs.
    responses=error_responses(401, 404, 422, 503),  # Documents the possible errors.
)  # Finish the route declaration.
def check_availability(  # Ask whether a field is free for an interval.
    field_id: uuid.UUID,  # The field from the URL.
    start: Annotated[UtcTimestamp, Query(description="Start, with a timezone offset, e.g. 2026-11-15T20:00:00-05:00")],  # Required start time.
    end: Annotated[UtcTimestamp, Query(description="End, with a timezone offset; must be after start")],  # Required end time.
    principal: Principal = Depends(get_current_principal),  # Login required.
    service: CatalogService = Depends(get_catalog_service_with_availability),  # Service with the engine attached.
) -> AvailabilityOut:  # Return the availability shape.
    # Advisory only: the booking endpoint makes the final decision.
    return service.check_availability(field_id, start, end)  # The service validates and asks the engine.
