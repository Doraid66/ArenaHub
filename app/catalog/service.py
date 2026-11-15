"""Catalog business logic: browsing fields and checking availability.

Availability is NOT calculated here. It is delegated to the shared reservation
engine (Person 1's ReservationService.is_available), so there is only one
conflict algorithm in the whole service.
"""

import uuid  # Field IDs are UUIDs.
from datetime import datetime, timezone  # Compare times and convert to UTC.
from typing import Protocol  # Describe the engine by its methods only.

from sqlalchemy.orm import Session  # The request's database session.

from app.catalog import repository  # Field queries.
from app.catalog.schemas import AvailabilityOut, FieldListOut, FieldOut  # Response shapes.
from app.core.errors import InvalidInputError, NotFoundError  # Shared 422 and 404 errors.


class AvailabilityChecker(Protocol):  # The interface the engine must offer.
    """Anything with this method can answer availability questions.

    The real one is Person 1's ReservationService; tests use a simple fake.
    """

    def is_available(self, field_id: uuid.UUID, start: datetime, end: datetime) -> bool: ...  # True when the interval is free.


def to_utc(value: datetime, name: str) -> datetime:  # Convert a timestamp to UTC.
    """Require an explicit timezone offset, then convert to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:  # No timezone offset given.
        raise InvalidInputError(f"'{name}' must include a timezone offset, e.g. 2026-11-15T20:00:00-05:00")  # Never guess a timezone.
    try:  # Conversion can overflow for extreme dates.
        return value.astimezone(timezone.utc)  # Same instant, expressed in UTC.
    except OverflowError:  # The UTC value would fall outside the supported range.
        # e.g. 0001-01-01T00:00:01+00:03 would be before year 1 in UTC (found by Schemathesis)
        raise InvalidInputError(f"'{name}' is out of range") from None  # Return a 422 instead of a 500.


class CatalogService:  # Rules for browsing fields and checking availability.
    def __init__(self, db: Session, availability: AvailabilityChecker | None = None) -> None:  # The engine is optional.
        self.db = db  # Keep the session for queries.
        self.availability = availability  # None when only browsing fields.

    def list_fields(self) -> FieldListOut:  # Return every field.
        fields = repository.list_fields(self.db)  # Load them in display order.
        return FieldListOut(items=[FieldOut.model_validate(f) for f in fields])  # Convert each to the public shape.

    def check_availability(self, field_id: uuid.UUID, start: datetime, end: datetime) -> AvailabilityOut:  # Is the field free?
        start_utc = to_utc(start, "start")  # Normalize the start.
        end_utc = to_utc(end, "end")  # Normalize the end.
        if end_utc <= start_utc:  # Empty or reversed interval.
            raise InvalidInputError("'end' must be after 'start'")  # Return a 422.
        if repository.get_field(self.db, field_id) is None:  # Unknown field.
            raise NotFoundError("Field not found")  # Return a 404.
        if self.availability is None:  # No engine was provided.
            raise RuntimeError("CatalogService needs an availability checker for this operation")  # A programming mistake, not user input.

        available = self.availability.is_available(field_id, start_utc, end_utc)  # Ask the shared engine.
        return AvailabilityOut(field_id=field_id, start=start_utc, end=end_utc, available=available)  # Echo the UTC times with the answer.
