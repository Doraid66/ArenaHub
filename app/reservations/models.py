"""The reservation and its retry receipt are saved in one database transaction."""

import uuid  # UUIDs identify reservations without a shared application counter.
from datetime import datetime  # Type hints describe the timestamp columns.
from typing import Any  # A stored JSON response contains several value types.

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, Uuid, func  # SQL column and constraint types.
from sqlalchemy.orm import Mapped, mapped_column  # SQLAlchemy's typed model declarations.

from app.core.database import Base  # All three teammates use the same metadata.


class Reservation(Base):  # Bookings and manager blocks compete in the same table.
    __tablename__ = "reservations"  # The table created by migration 0003.

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)  # Generated when the row is flushed.
    field_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("fields.id", ondelete="RESTRICT"))  # The reserved surface must exist.
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))  # The player or manager who created it.
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # Inclusive start of the playing interval.
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # Exclusive end allows adjacent reservations.
    kind: Mapped[str] = mapped_column(String(16))  # BOOKING or BLOCK.
    status: Mapped[str] = mapped_column(String(16))  # Lifecycle state, checked below.
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # Only a temporary booking needs a deadline.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())  # Database-generated audit time.

    __table_args__ = (  # Database constraints protect even writes outside the HTTP API.
        CheckConstraint("end_at > start_at", name="valid_interval"),  # Empty or reversed intervals are invalid.
        CheckConstraint("kind IN ('BOOKING', 'BLOCK')", name="valid_kind"),  # No unknown reservation kinds.
        CheckConstraint(  # Each kind has its own legal states.
            "(kind = 'BOOKING' AND status IN ('HELD', 'CONFIRMED', 'CANCELLED', 'EXPIRED')) "  # Booking lifecycle.
            "OR (kind = 'BLOCK' AND status IN ('ACTIVE', 'CANCELLED'))",  # Manager-block lifecycle.
            name="valid_kind_status",  # Base adds the ck_reservations_ prefix.
        ),  # Finish the kind/state check.
        CheckConstraint("status <> 'HELD' OR hold_expires_at IS NOT NULL", name="held_requires_expiry"),  # Holds must expire.
        Index("ix_reservations_field_interval", "field_id", "start_at", "end_at"),  # Supports overlap lookups by field.
        Index("ix_reservations_user_id", "user_id"),  # Supports owner lookups and the user foreign key.
    )  # Finish the table's constraints and indexes.


class IdempotencyRecord(Base):  # A durable receipt for one successful create request.
    __tablename__ = "idempotency_records"  # Shared by holds and blocks.

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)  # Internal receipt ID.
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))  # Keys belong to one caller.
    operation: Mapped[str] = mapped_column(String(40))  # Holds and blocks have separate key namespaces.
    key: Mapped[str] = mapped_column(String(200))  # The caller's opaque retry key.
    request_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 of the normalized request.
    response_status: Mapped[int] = mapped_column(Integer)  # Successful creates return 201.
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON)  # The original response survives restarts and later cancellation.

    __table_args__ = (  # PostgreSQL arbitrates duplicate keys across processes.
        UniqueConstraint("user_id", "operation", "key", name="uq_idempotency_records_scoped_key"),  # One receipt per caller, operation, and key.
    )  # Finish the uniqueness declaration.
