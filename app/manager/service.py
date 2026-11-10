"""Authorize blocks, then delegate all capacity writes to Person 1's engine."""

import uuid
from datetime import datetime
from typing import Protocol

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.catalog.repository import get_field
from app.core.errors import InvalidInputError, NotFoundError, ServiceUnavailableError
from app.core.principal import Principal, require_facility_manager
from app.core.timestamps import UtcTimestamp
from app.manager.schemas import BlockOut

_timestamp = TypeAdapter(UtcTimestamp)


class BlockWriter(Protocol):
    """Person 1 exposes this method on ReservationService(db)."""

    def create_block(
        self, principal: Principal, field_id: uuid.UUID,
        start: datetime, end: datetime, idempotency_key: str,
    ) -> BlockOut: ...


def get_reservation_writer(db: Session) -> BlockWriter:
    # Import only when needed, so login and forbidden-block checks work before merge.
    try:
        from app.reservations.service import ReservationService
    except ModuleNotFoundError as exc:
        if exc.name in ("app.reservations", "app.reservations.service"):
            raise ServiceUnavailableError("Reservation service is not available yet") from None
        raise
    return ReservationService(db)


class ManagerService:
    def __init__(self, db: Session, reservations: BlockWriter | None = None) -> None:
        self.db = db
        self.reservations = reservations

    def create_block(
        self, principal: Principal, field_id: uuid.UUID,
        start: datetime, end: datetime, idempotency_key: str,
    ) -> BlockOut:
        field = get_field(self.db, field_id)
        if field is None:
            raise NotFoundError("Field not found")
        # Service-layer check: a direct Python call must be authorized too.
        require_facility_manager(principal, field.facility_id, self.db)
        try:
            start = _timestamp.validate_python(start)
            end = _timestamp.validate_python(end)
        except ValidationError:
            raise InvalidInputError("Block times must include a valid timezone offset") from None
        if end <= start:
            raise InvalidInputError("'end' must be after 'start'")
        if not idempotency_key or len(idempotency_key) > 200 or not all(
            33 <= ord(character) <= 126 for character in idempotency_key
        ):
            raise InvalidInputError("Idempotency-Key must contain 1 to 200 visible ASCII characters")

        writer = self.reservations if self.reservations is not None else get_reservation_writer(self.db)
        # No commit, lock, conflict query, or idempotency storage here. The shared engine
        # owns that transaction and must invoke require_facility_manager at its write boundary.
        # It must replay a completed idempotency key BEFORE rejecting a newly requested
        # start in the past: a valid retry may arrive after the original block began.
        return writer.create_block(principal, field_id, start, end, idempotency_key)
