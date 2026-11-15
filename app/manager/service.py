"""Authorize blocks, then delegate all capacity writes to Person 1's engine."""

import uuid  # IDs are UUIDs.
from datetime import datetime  # Block start and end times.
from typing import Protocol  # Describe the engine by its methods only.

from pydantic import TypeAdapter, ValidationError  # Reuse the shared timestamp validator.
from sqlalchemy.orm import Session  # The request's database session.

from app.catalog.repository import get_field  # Look up the target field.
from app.core.errors import InvalidInputError, NotFoundError, ServiceUnavailableError  # Shared 422, 404, and 503 errors.
from app.core.principal import Principal, require_facility_manager  # The caller and the manager check.
from app.core.timestamps import UtcTimestamp  # Strict timestamp type with a required offset.
from app.manager.schemas import BlockOut  # The created block's shape.

_timestamp = TypeAdapter(UtcTimestamp)  # Build the reusable validator once.


class BlockWriter(Protocol):  # The interface the engine must offer.
    """Person 1 exposes this method on ReservationService(db)."""

    def create_block(  # Save a block and return it.
        self, principal: Principal, field_id: uuid.UUID,  # Who is blocking, and which field.
        start: datetime, end: datetime, idempotency_key: str,  # The interval and the retry key.
    ) -> BlockOut: ...  # The created block.


def get_reservation_writer(db: Session) -> BlockWriter:  # Find the real engine.
    # Import only when needed, so login and forbidden-block checks work before merge.
    try:  # The engine module may not exist yet.
        from app.reservations.service import ReservationService  # Import late, only when needed.
    except ModuleNotFoundError as exc:  # The import failed.
        if exc.name in ("app.reservations", "app.reservations.service"):  # The engine itself is missing.
            raise ServiceUnavailableError("Reservation service is not available yet") from None  # Answer 503 instead of crashing.
        raise  # The engine exists but has a broken import: show the real error.
    return ReservationService(db)  # Real engine on this request's session.


class ManagerService:  # Rules for manager blocks.
    def __init__(self, db: Session, reservations: BlockWriter | None = None) -> None:  # The engine can be injected for tests.
        self.db = db  # Keep the session for queries.
        self.reservations = reservations  # None means "find the real engine when needed".

    def create_block(  # Authorize, validate, then delegate the write.
        self, principal: Principal, field_id: uuid.UUID,  # Who is blocking, and which field.
        start: datetime, end: datetime, idempotency_key: str,  # The interval and the retry key.
    ) -> BlockOut:  # The created block.
        field = get_field(self.db, field_id)  # Load the target field.
        if field is None:  # Unknown field.
            raise NotFoundError("Field not found")  # Return a 404.
        # Service-layer check: a direct Python call must be authorized too.
        require_facility_manager(principal, field.facility_id, self.db)  # Raises 403 unless they manage this facility.
        try:  # Validate the times even for direct Python callers.
            start = _timestamp.validate_python(start)  # Normalize the start to UTC.
            end = _timestamp.validate_python(end)  # Normalize the end to UTC.
        except ValidationError:  # Naive or out-of-range time.
            raise InvalidInputError("Block times must include a valid timezone offset") from None  # Hide Pydantic details.
        if end <= start:  # Empty or reversed interval.
            raise InvalidInputError("'end' must be after 'start'")  # Return a 422.
        if not idempotency_key or len(idempotency_key) > 200 or not all(  # Key must be 1-200 characters.
            33 <= ord(character) <= 126 for character in idempotency_key  # Visible ASCII only.
        ):  # Finish the key check.
            raise InvalidInputError("Idempotency-Key must contain 1 to 200 visible ASCII characters")  # Return a 422.

        writer = self.reservations if self.reservations is not None else get_reservation_writer(self.db)  # Use the injected engine or the real one.
        # No commit, lock, conflict query, or idempotency storage here. The shared engine
        # owns that transaction and must invoke require_facility_manager at its write boundary.
        # It must replay a completed idempotency key BEFORE rejecting a newly requested
        # start in the past: a valid retry may arrive after the original block began.
        return writer.create_block(principal, field_id, start, end, idempotency_key)  # The engine does the locking and saving.
