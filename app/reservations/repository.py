"""Reservation SQL. The service decides when to commit or roll back."""

from datetime import datetime, timezone  # Expose aware UTC timestamps to the service.
from uuid import UUID  # Database identifiers use UUIDs.

from sqlalchemy import and_, func, or_, select  # Compose parameterized SQL expressions.
from sqlalchemy.orm import Session  # Use the shared request's session.

from app.catalog.models import Field  # Lock an existing field even when it has no reservations.
from app.reservations.models import IdempotencyRecord, Reservation  # The engine's two tables.


class ReservationRepository:  # SQL stays separate from request and lifecycle decisions.
    def __init__(self, db: Session) -> None:  # No second connection or transaction is created here.
        self.db = db  # Every query participates in the service's transaction.

    def database_now(self) -> datetime:  # PostgreSQL now() would be frozen at transaction start.
        return self.db.scalar(select(func.clock_timestamp())).astimezone(timezone.utc)  # Read actual database time, including time spent waiting for a lock.

    def lock_field_family(self, root_id: UUID) -> None:  # All capacity writes use this one stable row.
        self.db.execute(select(Field.id).where(Field.id == root_id).with_for_update()).scalar_one()  # Held until commit/rollback, across threads and API processes.

    def conflicting_field_ids(self, field: Field) -> set[UUID]:  # Encode the shared parent/child spatial rule once.
        if field.parent_field_id is not None:  # A child shares space with its parent, but not its siblings.
            return {field.id, field.parent_field_id}  # Different 7v7 fields may coexist.
        children = self.db.scalars(select(Field.id).where(Field.parent_field_id == field.id))  # A whole-field request overlaps all direct children.
        return {field.id, *children}  # A standalone field simply has no children.

    def has_conflict(self, field: Field, start: datetime, end: datetime, now: datetime) -> bool:  # Used by both availability and writes.
        active = or_(  # Cancelled and expired rows never occupy space.
            and_(Reservation.kind == "BOOKING", Reservation.status == "CONFIRMED"),  # Reserved for the later payment phase.
            and_(Reservation.kind == "BLOCK", Reservation.status == "ACTIVE"),  # Maintenance occupies space too.
            and_(Reservation.kind == "BOOKING", Reservation.status == "HELD", Reservation.hold_expires_at > now),  # An elapsed hold disappears from occupancy immediately.
        )  # Finish the active-state predicate.
        query = select(Reservation.id).where(  # Existence is enough; do not load every competing reservation.
            Reservation.field_id.in_(self.conflicting_field_ids(field)),  # Apply the spatial rule.
            Reservation.start_at < end,  # Strict comparison allows touching endpoints.
            Reservation.end_at > start,  # The second half of the overlap test.
            active,  # Only effective occupancy can reject this interval.
        ).limit(1)  # Stop at the first conflict.
        return self.db.scalar(query) is not None  # A conflicting row means unavailable.

    def get_reservation(self, reservation_id: UUID) -> Reservation | None:  # Refresh cached state after waiting on the family lock.
        return self.db.scalar(select(Reservation).where(Reservation.id == reservation_id).execution_options(populate_existing=True))  # None also covers unknown IDs.

    def get_idempotency_record(self, user_id: UUID, operation: str, key: str) -> IdempotencyRecord | None:  # Look up the caller's operation-specific receipt.
        return self.db.scalar(select(IdempotencyRecord).where(  # The unique constraint uses the same three columns.
            IdempotencyRecord.user_id == user_id,  # Another user may reuse the text of this key.
            IdempotencyRecord.operation == operation,  # A block key does not collide with a hold key.
            IdempotencyRecord.key == key,  # Match the opaque key exactly.
        ))  # No receipt means no successful attempt is committed yet.
