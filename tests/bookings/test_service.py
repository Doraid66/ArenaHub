"""Use-case tests against PostgreSQL, including expiry without sleeps."""

import uuid  # Unique request keys isolate attempts.
from datetime import timedelta, timezone  # Shift times and represent equivalent offsets.

import pytest  # Parametrization covers the spatial rule in both directions.
from sqlalchemy import event, func, select  # Inspect persisted state and inject an actual write failure.

from app.auth.demo_accounts import DEMO_MANAGER_ID, DEMO_PLAYER_1_ID, DEMO_PLAYER_2_ID  # Valid seeded foreign keys.
from app.catalog.demo_data import BASKETBALL_COURT_ID, FULL_SOCCER_FIELD_ID, OTHER_SOCCER_FIELD_ID, SUB_FIELD_A_ID, SUB_FIELD_B_ID  # Shared catalog IDs.
from app.core.config import get_settings  # The hold duration must remain configurable.
from app.core.database import engine  # Observe SQL only for the rollback regression test.
from app.core.errors import ForbiddenError, IdempotencyConflictError, InvalidInputError, NotFoundError, SlotUnavailableError  # Public service error types.
from app.core.principal import Principal  # Trusted service identity input.
from app.reservations.models import IdempotencyRecord, Reservation  # Verify rows, not only returned DTOs.

OWNER = Principal(DEMO_PLAYER_1_ID)  # First seeded player.
OTHER = Principal(DEMO_PLAYER_2_ID)  # Separate identity for capacity and ownership checks.
MANAGER = Principal(DEMO_MANAGER_ID)  # Manager of the demo facility only.


def hold(service, window, field=BASKETBALL_COURT_ID, principal=OWNER, key=None):  # Small public-use-case helper.
    return service.create_hold(principal, field, *window, key or str(uuid.uuid4()))  # New key unless a test requests a replay.


@pytest.mark.parametrize("first,second", [(BASKETBALL_COURT_ID, BASKETBALL_COURT_ID), (FULL_SOCCER_FIELD_ID, SUB_FIELD_A_ID), (SUB_FIELD_A_ID, FULL_SOCCER_FIELD_ID)])  # Same field and both parent/child directions.
def test_overlapping_space_rejects_second_hold(service, window, first, second):  # Spatial conflicts are independent of ownership.
    hold(service, window, first)  # Establish active occupancy.
    with pytest.raises(SlotUnavailableError):  # The second player must not double-book it.
        hold(service, window, second, OTHER)  # Use a different key and real user.


def test_adjacent_intervals_and_different_children_can_coexist(service, window):  # Serialization must not over-restrict capacity.
    start, end = window  # Original one-hour interval.
    hold(service, window, SUB_FIELD_A_ID)  # First child is occupied.
    hold(service, window, SUB_FIELD_B_ID, OTHER)  # A sibling uses different space.
    hold(service, (end, end + timedelta(hours=1)), SUB_FIELD_A_ID, OTHER)  # A touching interval shares no time.
    assert not service.is_available(FULL_SOCCER_FIELD_ID, start, end)  # Occupied children still block the whole field.


def test_partial_overlap_and_containment_conflict(service, window):  # Exact interval equality is not required for a conflict.
    start, end = window  # Establish the reference interval.
    hold(service, window)  # Reserve it once.
    for requested in [(start + timedelta(minutes=30), end + timedelta(minutes=30)), (start - timedelta(minutes=30), end + timedelta(minutes=30))]:  # Partial overlap and enclosing interval.
        with pytest.raises(SlotUnavailableError):  # Both would consume already-held time.
            hold(service, requested, principal=OTHER)  # Do not reuse the original key.


def test_expiry_boundary_releases_space_and_late_cancel_never_revives_it(service, booking_db, window, monkeypatch):  # No sleeps or cleanup worker needed.
    now = service.repository.database_now()  # Anchor a deterministic database-clock substitute.
    monkeypatch.setattr(service.repository, "database_now", lambda: now)  # Every operation sees the chosen instant.
    booking = hold(service, window)  # Save the hold at the anchored time.
    booking_id = uuid.UUID(booking["id"])  # Public ID for read/cancel calls.
    expiry = now + timedelta(minutes=get_settings().hold_minutes)  # The configured lifetime determines the boundary.
    assert booking_db.get(Reservation, booking_id).hold_expires_at == expiry  # The server, not the caller, calculated the deadline.
    monkeypatch.setattr(service.repository, "database_now", lambda: expiry)  # Exactly at the deadline, not one second later.
    assert service.get_booking(OWNER, booking_id)["status"] == "EXPIRED"  # GET uses effective expiry.
    assert service.is_available(BASKETBALL_COURT_ID, *window)  # An elapsed HELD row stops occupying space immediately.
    service.cancel_booking(OWNER, booking_id)  # Late cancellation still succeeds.
    service.cancel_booking(OWNER, booking_id)  # Repeating it is safe too.
    assert service.get_booking(OWNER, booking_id)["status"] == "EXPIRED"  # Never report it as a newly active hold.
    hold(service, window, principal=OTHER)  # Another player can now reserve the released interval.


def test_confirmed_booking_still_occupies_after_its_old_hold_deadline(service, booking_db, window):  # Preserve the planned payment integration's state rule.
    booking = hold(service, window)  # Create a valid booking first.
    row = booking_db.get(Reservation, uuid.UUID(booking["id"]))  # Adjust state as a future payment worker would.
    row.status = "CONFIRMED"  # Confirmed occupancy no longer depends on hold expiry.
    row.hold_expires_at = service.repository.database_now() - timedelta(days=1)  # Its former hold deadline has passed.
    booking_db.commit()  # Make the fixture state visible to the conflict query.
    assert not service.is_available(BASKETBALL_COURT_ID, *window)  # Confirmed reservations continue to reserve space.


def test_cancel_releases_space_and_is_owner_only(service, window):  # Authorization must apply to direct service callers.
    booking_id = uuid.UUID(hold(service, window)["id"])  # Create an owned booking.
    for action in [service.get_booking, service.cancel_booking]:  # Both use cases protect the same resource.
        with pytest.raises(NotFoundError):  # Do not reveal its existence to another player.
            action(OTHER, booking_id)  # Another authenticated user is insufficient.
    service.cancel_booking(OWNER, booking_id)  # The owner can release it.
    service.cancel_booking(OWNER, booking_id)  # Repetition returns normally.
    assert service.get_booking(OWNER, booking_id)["status"] == "CANCELLED"  # GET exposes the persisted transition.
    assert service.is_available(BASKETBALL_COURT_ID, *window)  # The cancellation changed actual capacity.


def test_retry_replays_original_snapshot_after_cancel_and_start(service, booking_db, window, monkeypatch):  # A retry must not recreate cancelled occupancy.
    key = str(uuid.uuid4())  # Reuse exactly one caller/operation key.
    first = hold(service, window, key=key)  # Original successful response.
    service.cancel_booking(OWNER, uuid.UUID(first["id"]))  # The resource subsequently changed.
    monkeypatch.setattr(service.repository, "database_now", lambda: window[1] + timedelta(days=1))  # Retry arrives after the playing interval too.
    assert hold(service, window, key=key) == first  # Reproduce the original HELD response and ID.
    assert service.get_booking(OWNER, uuid.UUID(first["id"]))["status"] == "CANCELLED"  # GET remains the current-state endpoint.
    assert booking_db.scalar(select(func.count()).select_from(Reservation)) == 1  # No second resource was created.


def test_equivalent_offsets_replay_and_changed_payload_conflicts(service, window):  # Canonicalization compares instants, not timestamp spelling.
    key = str(uuid.uuid4())  # One key for this use case.
    first = hold(service, window, key=key)  # UTC payload.
    shifted = tuple(value.astimezone(timezone(timedelta(hours=-5))) for value in window)  # Same instants with another offset.
    assert hold(service, shifted, key=key) == first  # Equivalent payload is a replay.
    with pytest.raises(IdempotencyConflictError):  # A changed interval cannot reuse the same key.
        hold(service, (window[0], window[1] + timedelta(minutes=1)), key=key)  # Only end differs.
    with pytest.raises(IdempotencyConflictError):  # The field is part of the fingerprint too.
        hold(service, window, SUB_FIELD_A_ID, key=key)  # Different field, same caller and operation.


def test_keys_are_scoped_by_user_and_operation(service, booking_db, window):  # Reusing the key text across namespaces is legal.
    key = str(uuid.uuid4())  # Deliberately identical text.
    hold(service, window, SUB_FIELD_A_ID, OWNER, key)  # First user namespace.
    hold(service, window, SUB_FIELD_B_ID, OTHER, key)  # Another user namespace.
    hold(service, window, BASKETBALL_COURT_ID, MANAGER, key)  # Manager's booking operation.
    service.create_block(MANAGER, FULL_SOCCER_FIELD_ID, window[1], window[1] + timedelta(hours=1), key)  # Manager's separate block operation.
    assert booking_db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 4  # Four independent receipts.


def test_block_authorization_conflicts_replay_and_booking_exclusion(service, window, monkeypatch):  # Exercise the agreed Person 2 write boundary.
    for principal, field in [(OWNER, BASKETBALL_COURT_ID), (MANAGER, OTHER_SOCCER_FIELD_ID)]:  # Player and manager of another facility.
        with pytest.raises(ForbiddenError):  # The engine must independently invoke the manager guard.
            service.create_block(principal, field, *window, str(uuid.uuid4()))  # Direct call bypasses the HTTP facade.
    key = str(uuid.uuid4())  # Reuse for the manager's retry.
    block = service.create_block(MANAGER, BASKETBALL_COURT_ID, *window, key)  # Real authorized manager creates occupancy.
    with pytest.raises(SlotUnavailableError):  # Bookings compete with active blocks.
        hold(service, window)  # Same field and interval.
    with pytest.raises(NotFoundError):  # A block is never retrievable as a booking, even by its owner.
        service.get_booking(MANAGER, uuid.UUID(block["id"]))  # The kind check matters as well as ownership.
    with pytest.raises(NotFoundError):  # Cancellation must also exclude blocks.
        service.cancel_booking(MANAGER, uuid.UUID(block["id"]))  # Booking DELETE cannot remove maintenance.
    monkeypatch.setattr(service.repository, "database_now", lambda: window[1] + timedelta(days=1))  # Retry after the block began.
    assert service.create_block(MANAGER, BASKETBALL_COURT_ID, *window, key) == block  # Replay precedes the new-request past-time rule.


@pytest.mark.parametrize("key", ["", "has space", "line\n", "é", "x" * 201])  # Match the HTTP header's visible-ASCII restrictions.
def test_direct_service_rejects_invalid_retry_keys(service, window, key):  # Validation cannot live only in FastAPI.
    with pytest.raises(InvalidInputError):  # Expected domain error, not a database failure.
        service.create_hold(OWNER, BASKETBALL_COURT_ID, *window, key)  # Pass the invalid key unchanged, including the empty string.


def test_invalid_intervals_and_unknown_ids(service, window):  # Validate before writing any capacity.
    for interval in [(window[1], window[0]), (window[0], window[0]), (window[0].replace(tzinfo=None), window[1]), (window[0] - timedelta(days=10), window[1])]:  # Reversed, empty, naive, and past starts.
        with pytest.raises(InvalidInputError):  # These are all caller input errors.
            hold(service, interval)  # No successful receipt should be persisted.
    with pytest.raises(NotFoundError):  # A random UUID is syntactically valid but unknown.
        hold(service, window, uuid.uuid4())  # Missing catalog row.
    with pytest.raises(NotFoundError):  # Unknown bookings use the same non-disclosing error.
        service.get_booking(OWNER, uuid.uuid4())  # No HTTP route is needed to enforce it.


def test_receipt_failure_rolls_back_the_already_flushed_reservation(service, booking_db, window):  # Reproduce the dangerous half-write failure.
    def fail_receipt(connection, cursor, statement, parameters, context, executemany):  # Observe an actual PostgreSQL INSERT.
        if statement.startswith("INSERT INTO idempotency_records"):  # Reservation INSERT has already succeeded in the transaction.
            raise RuntimeError("Injected receipt write failure")  # Simulate a later persistence failure.
    event.listen(engine, "before_cursor_execute", fail_receipt)  # Scope the fault injection to this test.
    try:  # Always restore normal SQL execution.
        with pytest.raises(RuntimeError, match="Injected receipt"):  # The service must roll back and propagate the failure.
            hold(service, window)  # Start a real write, not a mocked repository transaction.
    finally:  # Avoid contaminating later tests.
        event.remove(engine, "before_cursor_execute", fail_receipt)  # Remove the SQL hook.
    assert booking_db.scalar(select(func.count()).select_from(Reservation)) == 0  # The flushed reservation was not committed alone.
    assert booking_db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0  # There is no incomplete replay receipt either.
    hold(service, window)  # Rollback left the session reusable and capacity free.


def test_database_clock_advances_inside_an_already_open_transaction(service, booking_db):  # PostgreSQL now() is frozen for an entire transaction.
    transaction_start = booking_db.scalar(select(func.now()))  # Authentication-style read starts the transaction.
    actual_now = service.repository.database_now()  # This must call clock_timestamp(), not now().
    assert actual_now > transaction_start  # A later statement observes actual time without an artificial sleep.


def test_availability_does_not_commit_unrelated_work(service, booking_db, window):  # Advisory reads must not become write boundaries.
    row = Reservation(field_id=BASKETBALL_COURT_ID, user_id=OWNER.user_id, start_at=window[0], end_at=window[1], kind="BOOKING", status="CANCELLED")  # Stage valid unrelated test data.
    booking_db.add(row)  # The pending row belongs to the caller's transaction.
    assert service.is_available(BASKETBALL_COURT_ID, *window)  # Read-only lookup must leave it pending.
    booking_db.rollback()  # Discard the staged data.
    assert booking_db.scalar(select(func.count()).select_from(Reservation)) == 0  # A hidden commit would have made the row survive rollback.
