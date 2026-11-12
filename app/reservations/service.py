"""One transaction owns the family lock, conflict decision, reservation, and receipt."""

import logging  # Reuse the application's correlation-aware logging.
from datetime import datetime, timedelta, timezone  # Calculate hold deadlines using database time.
from typing import Any  # Both booking and block results are JSON-compatible mappings.
from uuid import UUID  # Service identifiers match the public API.

from sqlalchemy.exc import IntegrityError  # Handle the database's duplicate-key arbitration.
from sqlalchemy.orm import Session  # Authentication may already have begun this session's transaction.

from app.catalog.models import Field  # Type the catalog objects without redefining their schema.
from app.catalog.repository import get_field  # Reuse Person 3's field lookup.
from app.core.config import get_settings  # HOLD_MINUTES controls the demo's lifetime.
from app.core.errors import IdempotencyConflictError, NotFoundError, SlotUnavailableError  # Shared domain errors become HTTP responses centrally.
from app.core.principal import Principal, require_facility_manager  # Identity and current manager membership come from Person 2.
from app.reservations.models import IdempotencyRecord, Reservation  # Store occupancy and replay data atomically.
from app.reservations.repository import ReservationRepository  # Keep SQL in the data-source layer.
from app.reservations.rules import (  # Reuse the same rules across entry points.
    effective_status,  # An elapsed hold is expired even before a cleanup job.
    normalize_interval,  # Direct callers use the same UTC validation as HTTP.
    request_fingerprint,  # Equivalent requests produce the same canonical digest.
    validate_future_start,  # Only new reservations must still start in the future.
    validate_key,  # Internal callers obey the published retry-key contract too.
)  # Finish the shared rule imports.

logger = logging.getLogger(__name__)  # Never log keys, credentials, or request bodies.


class ReservationService:  # The catalog and manager facade both depend on this interface.
    def __init__(self, db: Session) -> None:  # Keep the constructor agreed with both teammates.
        self.db = db  # The service owns commit/rollback on this request-scoped session.
        self.repository = ReservationRepository(db)  # Queries share the exact same transaction.

    def create_hold(  # Player booking use case.
        self, principal: Principal, field_id: UUID,  # Trusted caller and requested surface.
        start: datetime, end: datetime, idempotency_key: str,  # Playing interval and retry identity.
    ) -> dict[str, Any]:  # Return a DTO, not a database object.
        return self._create_reservation(principal, field_id, start, end, idempotency_key, "BOOKING")  # All creates go through one conflict engine.

    def create_block(  # Manager facade's agreed integration method.
        self, principal: Principal, field_id: UUID,  # Current manager and target surface.
        start: datetime, end: datetime, idempotency_key: str,  # Block interval and retry identity.
    ) -> dict[str, Any]:  # Keep the exact constructor and argument agreement with Person 2.
        return self._create_reservation(principal, field_id, start, end, idempotency_key, "BLOCK")  # Manager authorization is also enforced inside this engine.

    def is_available(self, field_id: UUID, start: datetime, end: datetime) -> bool:  # Advisory read, with no lock or commit.
        start, end = normalize_interval(start, end)  # Apply interval rules even to direct Python callers.
        field = self._field(field_id)  # Unknown fields use the shared 404 error.
        return not self.repository.has_conflict(field, start, end, self.repository.database_now())  # Exactly the same overlap predicate as a write.

    def get_booking(self, principal: Principal, booking_id: UUID) -> dict[str, Any]:  # A read never changes an elapsed hold back to HELD.
        booking = self._owned_booking(principal, booking_id)  # Ownership belongs in the service, not just the route.
        return self._response(booking, self.repository.database_now())  # GET reports the current effective state.

    def cancel_booking(self, principal: Principal, booking_id: UUID) -> None:  # Repeating cancellation is naturally idempotent.
        try:  # Any failure must release locks and discard partial writes.
            booking = self._owned_booking(principal, booking_id)  # Hide unknown, foreign-owned, and BLOCK IDs behind 404.
            field = self._field(booking.field_id)  # Find the stable family row.
            self.repository.lock_field_family(field.parent_field_id or field.id)  # Cancellation uses the same lock as creation.
            booking = self._owned_booking(principal, booking_id)  # Re-read after waiting so two cancels cannot use stale state.
            status = effective_status(booking.status, booking.hold_expires_at, self.repository.database_now())  # Expiry still wins over late cancellation.
            booking.status = "EXPIRED" if status == "EXPIRED" else "CANCELLED"  # Repeated calls never revive occupancy.
            self.db.commit()  # Persist the transition and release the family lock together.
        except Exception:  # Includes domain errors and database failures.
            self.db.rollback()  # Leave the session reusable and release any lock.
            raise  # The central handler maps the original error.

    def _create_reservation(  # Shared write boundary for holds and blocks.
        self, principal: Principal, field_id: UUID,  # Owner identity and catalog surface.
        start: datetime, end: datetime, key: str, kind: str,  # Normalized below before any write.
    ) -> dict[str, Any]:  # Both use cases produce a replayable response mapping.
        operation = "create_hold" if kind == "BOOKING" else "create_block"  # Scope retries by use case, not by field.
        try:  # Reuse autobegun auth reads instead of nesting db.begin().
            start, end = normalize_interval(start, end)  # Normalize before hashing equivalent timestamps.
            validate_key(key)  # Defend direct service calls as well as HTTP calls.
            fingerprint = request_fingerprint(field_id, start, end)  # A changed field or interval must reject key reuse.
            field = self._field(field_id)  # Use the existing catalog lookup.
            if kind == "BLOCK":  # Never rely solely on the manager facade's earlier check.
                require_facility_manager(principal, field.facility_id, self.db)  # Even replay requires current authorization.
            response = self._replay(principal.user_id, operation, key, fingerprint)  # Replay before time-sensitive or occupancy checks.
            if response is None:  # No committed success is visible yet.
                self.repository.lock_field_family(field.parent_field_id or field.id)  # READ COMMITTED waits for the current writer.
                response = self._replay(principal.user_id, operation, key, fingerprint)  # A duplicate may have completed while we waited.
                if response is None:  # This caller must perform the actual create.
                    now = self.repository.database_now()  # Read wall-clock database time after acquiring the lock.
                    validate_future_start(start, now)  # New past requests fail; previously completed requests already replayed.
                    if self.repository.has_conflict(field, start, end, now):  # Run this query after the lock, in the same transaction.
                        raise SlotUnavailableError()  # The waiting loser sees the committed winner.
                    reservation = Reservation(  # Build a single occupancy row.
                        field_id=field_id, user_id=principal.user_id, start_at=start, end_at=end, kind=kind,  # Ownership is never supplied in a request body.
                        status="HELD" if kind == "BOOKING" else "ACTIVE",  # Milestone holds are never paid/confirmed.
                        hold_expires_at=(  # Calculate expiry from the time obtained after the lock wait.
                            now + timedelta(minutes=get_settings().hold_minutes) if kind == "BOOKING" else None  # Blocks have no hold deadline.
                        ),  # HOLD_MINUTES stays configurable for the demo.
                    )  # Blocks have no temporary expiry.
                    self.db.add(reservation)  # Stage occupancy in this transaction.
                    self.db.flush()  # Obtain its generated UUID without committing.
                    response = self._response(reservation, now)  # Store a JSON-safe snapshot, not a live ORM object.
                    self.db.add(IdempotencyRecord(  # Receipt and occupancy must succeed or fail together.
                        user_id=principal.user_id, operation=operation, key=key, request_hash=fingerprint,  # Match the unique scope.
                        response_status=201, response_body=response,  # Preserve the original resource ID and response.
                    ))  # The unique constraint also covers races across different field families.
            self.db.commit()  # One atomic commit; this also releases any family lock.
            return response  # The route handles the HTTP status and response schema.
        except IntegrityError as error:  # Another family may have used the same scoped key concurrently.
            self.db.rollback()  # Remove this transaction's reservation before reading the winner.
            if getattr(getattr(error.orig, "diag", None), "constraint_name", None) != "uq_idempotency_records_scoped_key":  # Do not disguise unrelated integrity failures.
                raise  # A foreign-key or schema problem needs the normal server error handling.
            try:  # The unique violation means PostgreSQL has finished waiting for the competing receipt.
                response = self._replay(principal.user_id, operation, key, fingerprint)  # Same payload replays; a different payload raises 409.
                if response is None:  # A missing winner would violate the retry protocol.
                    raise error  # Preserve the unexpected database failure.
                self.db.commit()  # End the fresh receipt-reading transaction.
                logger.info("Replayed a concurrent reservation request")  # Deliberately omit the request and key.
                return response  # No orphan reservation survives the earlier rollback.
            except Exception:  # Also clean up a conflicting-payload retry.
                self.db.rollback()  # Do not leave a newly opened transaction behind.
                raise  # Keep the domain error or unexpected failure intact.
        except Exception:  # Validation, authorization, missing fields, and capacity failures all land here.
            self.db.rollback()  # Authentication's autobegun transaction is included.
            raise  # Let the shared handler build the response.

    def _replay(self, user_id: UUID, operation: str, key: str, fingerprint: str) -> dict[str, Any] | None:  # Read completed successes only.
        record = self.repository.get_idempotency_record(user_id, operation, key)  # Unique scope identifies one original request.
        if record is None:  # A failed transaction leaves no receipt.
            return None  # The caller may attempt a new reservation.
        if record.request_hash != fingerprint:  # The key cannot be repurposed for another payload.
            raise IdempotencyConflictError()  # Distinct from a field-occupancy conflict.
        return dict(record.response_body)  # Reproduce the original snapshot even if the booking later expired.

    def _field(self, field_id: UUID) -> Field:  # Keep the existing lookup and error consistent across use cases.
        field = get_field(self.db, field_id)  # Person 3 owns field persistence.
        if field is None:  # Do not turn an unknown ID into a foreign-key failure.
            raise NotFoundError("Field not found")  # The public API documents 404.
        return field  # The caller only reads or locks this catalog object.

    def _owned_booking(self, principal: Principal, booking_id: UUID) -> Reservation:  # Shared read/cancel authorization.
        booking = self.repository.get_reservation(booking_id)  # Refresh state if this session saw it before locking.
        if booking is None or booking.kind != "BOOKING" or booking.user_id != principal.user_id:  # Manager blocks are never bookings.
            raise NotFoundError("Booking not found")  # Do not disclose another user's resource.
        return booking  # Only an owned booking crosses this boundary.

    def _response(self, reservation: Reservation, now: datetime) -> dict[str, Any]:  # JSON-compatible values can be stored and replayed exactly.
        result: dict[str, Any] = {  # Hold and block responses share these fields.
            "id": str(reservation.id), "field_id": str(reservation.field_id),  # Stable identifiers, not internal ORM objects.
            "status": effective_status(reservation.status, reservation.hold_expires_at, now),  # No expiry worker is required for correct reads.
            "start": reservation.start_at.astimezone(timezone.utc).isoformat(),  # Always emit UTC instants.
            "end": reservation.end_at.astimezone(timezone.utc).isoformat(),  # Preserve the exclusive endpoint.
        }  # Finish the common response.
        if reservation.kind == "BOOKING":  # Blocks intentionally omit the hold-only property.
            result["hold_expires_at"] = (  # Future confirmed bookings may omit a hold deadline.
                reservation.hold_expires_at.astimezone(timezone.utc).isoformat() if reservation.hold_expires_at else None  # Serialize the saved UTC deadline.
            )  # The caller cannot choose or extend this time.
        return result  # The HTTP schema validates this mapping at the boundary.
