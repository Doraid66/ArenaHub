"""Catalog business logic: browsing fields and checking availability.

Availability is NOT calculated here. It is delegated to the shared reservation
engine (Person 1's ReservationService.is_available), so there is only one
conflict algorithm in the whole service.
"""

import uuid
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from app.catalog import repository
from app.catalog.schemas import AvailabilityOut, FieldListOut, FieldOut
from app.core.errors import InvalidInputError, NotFoundError


class AvailabilityChecker(Protocol):
    """Anything with this method can answer availability questions.

    The real one is Person 1's ReservationService; tests use a simple fake.
    """

    def is_available(self, field_id: uuid.UUID, start: datetime, end: datetime) -> bool: ...


def to_utc(value: datetime, name: str) -> datetime:
    """Require an explicit timezone offset, then convert to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidInputError(f"'{name}' must include a timezone offset, e.g. 2026-11-15T20:00:00-05:00")
    try:
        return value.astimezone(timezone.utc)
    except OverflowError:
        # e.g. 0001-01-01T00:00:01+00:03 would be before year 1 in UTC (found by Schemathesis)
        raise InvalidInputError(f"'{name}' is out of range") from None


class CatalogService:
    def __init__(self, db: Session, availability: AvailabilityChecker | None = None) -> None:
        self.db = db
        self.availability = availability

    def list_fields(self) -> FieldListOut:
        fields = repository.list_fields(self.db)
        return FieldListOut(items=[FieldOut.model_validate(f) for f in fields])

    def check_availability(self, field_id: uuid.UUID, start: datetime, end: datetime) -> AvailabilityOut:
        start_utc = to_utc(start, "start")
        end_utc = to_utc(end, "end")
        if end_utc <= start_utc:
            raise InvalidInputError("'end' must be after 'start'")
        if repository.get_field(self.db, field_id) is None:
            raise NotFoundError("Field not found")
        if self.availability is None:
            raise RuntimeError("CatalogService needs an availability checker for this operation")

        available = self.availability.is_available(field_id, start_utc, end_utc)
        return AvailabilityOut(field_id=field_id, start=start_utc, end=end_utc, available=available)