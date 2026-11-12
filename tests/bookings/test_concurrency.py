"""Independent PostgreSQL connections prove capacity and retry safety under races."""

import uuid  # Distinct keys keep capacity tests separate from retry tests.
from concurrent.futures import ThreadPoolExecutor  # Hold one family lock while another connection tries to write.
from datetime import timedelta  # Build partially overlapping and adjacent windows.
from threading import Barrier, Event  # Synchronize writes and observe the moment a worker requests its family lock.

import pytest  # Parameterize every required spatial scenario.
from sqlalchemy import event, func, select  # Check persisted row counts and synchronize the unique-key race.

from app.auth.demo_accounts import DEMO_MANAGER_ID, DEMO_PLAYER_1_ID, DEMO_PLAYER_2_ID  # Real database users.
from app.catalog.demo_data import BASKETBALL_COURT_ID, FOOTBALL_FIELD_ID, FULL_SOCCER_FIELD_ID, SUB_FIELD_A_ID, SUB_FIELD_B_ID  # Stable demo surfaces.
from app.core.database import SessionLocal, engine  # Attach SQL observers and open independent sessions.
from app.core.errors import InvalidInputError  # A new start that passed while waiting must be rejected.
from app.core.principal import Principal  # Direct calls use the existing trusted identity interface.
from app.reservations.models import IdempotencyRecord, Reservation  # Inspect committed database occupancy.
from app.reservations.repository import ReservationRepository  # The clock is injectable without sleeping for a real hold lifetime.
from app.reservations.service import ReservationService  # Exercise the actual lock/check/write sequence.
from scripts.concurrency_demo import Attempt, inspect_occupancy, run_parallel_attempts  # Same real service-based harness used during the demo.


@pytest.mark.parametrize("first,second,offset,kind,expected", [  # Every case uses distinct callers and distinct keys.
    (BASKETBALL_COURT_ID, BASKETBALL_COURT_ID, 0, "BOOKING", 1),  # Exact same slot.
    (BASKETBALL_COURT_ID, BASKETBALL_COURT_ID, 30, "BOOKING", 1),  # Partial overlap.
    (FULL_SOCCER_FIELD_ID, SUB_FIELD_A_ID, 0, "BOOKING", 1),  # Whole field against child.
    (SUB_FIELD_A_ID, FULL_SOCCER_FIELD_ID, 0, "BOOKING", 1),  # Child against whole field.
    (SUB_FIELD_A_ID, SUB_FIELD_B_ID, 0, "BOOKING", 2),  # Independent children both fit.
    (BASKETBALL_COURT_ID, BASKETBALL_COURT_ID, 60, "BOOKING", 2),  # Adjacent half-open intervals.
    (SUB_FIELD_A_ID, FULL_SOCCER_FIELD_ID, 0, "BLOCK", 1),  # Manager block and player hold share the lock.
])  # Finish the spatial race cases.
def test_capacity_races_have_the_expected_occupancy(booking_db, window, first, second, offset, kind, expected):  # Sessions really commit concurrently.
    start, end = window  # Future one-hour interval.
    attempts = [  # Synchronization happens only after both workers have connected.
        Attempt(DEMO_PLAYER_1_ID, first, start, end, str(uuid.uuid4())),  # First authenticated service identity.
        Attempt(DEMO_MANAGER_ID if kind == "BLOCK" else DEMO_PLAYER_2_ID, second, start + timedelta(minutes=offset), end + timedelta(minutes=offset), str(uuid.uuid4()), kind),  # Distinct user and key.
    ]  # No duplicate-key shortcut can cause these capacity rejections.
    results = run_parallel_attempts(attempts)  # Separate sessions, backend PIDs, and synchronized starts.
    assert len({result.backend_pid for result in results}) == 2  # Demonstrate independent connections.
    assert sum(result.status == 201 for result in results) == expected  # Correct number of successful writes.
    assert len(inspect_occupancy(results)) == expected  # Returned successes agree with committed resources.
    assert booking_db.scalar(select(func.count()).select_from(Reservation)) == expected  # Also catch any orphan rows from rejected transactions.
    assert booking_db.scalar(select(func.count()).select_from(IdempotencyRecord)) == expected  # Every winner has one atomic receipt.


def test_many_contenders_still_create_one_booking(booking_db, window):  # More than two threads exercise waiting writers repeatedly.
    attempts = [Attempt(DEMO_PLAYER_1_ID if index % 2 else DEMO_PLAYER_2_ID, BASKETBALL_COURT_ID, *window, str(uuid.uuid4())) for index in range(8)]  # All keys are distinct.
    results = run_parallel_attempts(attempts)  # Eight real simultaneous PostgreSQL connections.
    assert len({result.backend_pid for result in results}) == 8  # No shared-session test shortcut.
    assert [result.status for result in results].count(201) == 1  # Exactly one winner.
    assert [result.status for result in results].count(409) == 7  # Seven controlled capacity rejections.
    assert booking_db.scalar(select(func.count()).select_from(Reservation)) == 1  # No hidden extra occupancy.


def test_simultaneous_duplicate_key_replays_one_resource(booking_db, window):  # Retry correctness is separate from distinct-key contention.
    attempt = Attempt(DEMO_PLAYER_1_ID, BASKETBALL_COURT_ID, *window, str(uuid.uuid4()))  # Same caller and canonical payload.
    results = run_parallel_attempts([attempt] * 4)  # Four concurrent deliveries of one logical request.
    assert all(result.status == 201 for result in results)  # Every delivery gets the successful receipt.
    assert all(result.body == results[0].body for result in results)  # Same resource ID and original snapshot.
    assert booking_db.scalar(select(func.count()).select_from(Reservation)) == 1  # Only one capacity change.
    assert booking_db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1  # Only one completed receipt.


def test_different_families_same_key_roll_back_the_unique_constraint_loser(booking_db, window):  # Force the cross-family race the root lock cannot serialize.
    key = str(uuid.uuid4())  # Both requests share user, operation, and key but have different fields.
    barrier = Barrier(2)  # Both reservations must be flushed before either receipt can win.

    def wait_at_receipt(connection, cursor, statement, parameters, context, executemany):  # Synchronize actual SQL, not a mocked service result.
        if statement.startswith("INSERT INTO idempotency_records"):  # Each transaction already owns a different family's row lock.
            barrier.wait(timeout=15)  # Ensure both attempted reservations exist before testing the unique constraint.

    attempts = [Attempt(DEMO_PLAYER_1_ID, field, *window, key) for field in [BASKETBALL_COURT_ID, FOOTBALL_FIELD_ID]]  # Different field families avoid serializing on one root.
    event.listen(engine, "before_cursor_execute", wait_at_receipt)  # Install the narrowly scoped synchronization hook.
    try:  # Always remove the hook before later tests or SQL writes.
        results = run_parallel_attempts(attempts)  # The unique receipt constraint must select one winner.
    finally:  # Even a test failure must not strand another test at this barrier.
        event.remove(engine, "before_cursor_execute", wait_at_receipt)  # Restore ordinary SQL execution.
    assert sorted(result.status for result in results) == [201, 409]  # Different payloads cannot both claim the key.
    assert next(result for result in results if result.status == 409).body["code"] == "idempotency_conflict"  # Not a raw integrity error or capacity rejection.
    assert booking_db.scalar(select(func.count()).select_from(Reservation)) == 1  # Losing reservation INSERT was rolled back.
    assert booking_db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1  # Winner's receipt remains intact.


@pytest.mark.parametrize("scenario", ["expiry", "past_start"])  # Both decisions must use time sampled after the lock wait.
def test_clock_is_read_after_waiting_for_the_family_lock(service, booking_db, monkeypatch, scenario):  # Deterministic time advancement; no sleeping.
    now = service.repository.database_now()  # Start with a real aware UTC database timestamp.
    clock = [now]  # A mutable test clock can advance while the writer is waiting.
    monkeypatch.setattr(ReservationRepository, "database_now", lambda self: clock[0])  # Every service instance sees the same controlled database time.
    start = now + timedelta(hours=1) if scenario == "expiry" else now + timedelta(minutes=5)  # One remains future after expiry; the other becomes past.
    end = start + timedelta(hours=1)  # Both scenarios request a valid-length interval.
    if scenario == "expiry":  # Establish occupancy that will expire during the wait.
        service.create_hold(Principal(DEMO_PLAYER_1_ID), BASKETBALL_COURT_ID, start, end, str(uuid.uuid4()))  # This hold's deadline is relative to the original clock.
    booking_db.rollback()  # Release any test-session read transaction before starting the controlled lock holder.
    requested_lock = Event()  # The worker announces its lock query without a timing-based sleep.

    def observe_lock(connection, cursor, statement, parameters, context, executemany):  # Called immediately before the worker's SQL lock request.
        if "FOR UPDATE" in statement:  # The main thread acquired its lock before this observer was installed.
            requested_lock.set()  # The worker has reached the serialization boundary.

    def write():  # This worker never shares the holder's connection or session.
        with SessionLocal() as db:  # Its transaction begins before it gets the family lock.
            db.scalar(select(func.now()))  # Reproduce authentication's earlier transaction start.
            return ReservationService(db).create_hold(Principal(DEMO_PLAYER_2_ID), BASKETBALL_COURT_ID, start, end, str(uuid.uuid4()))  # The real engine must wait for the root row.

    with SessionLocal() as holder, ThreadPoolExecutor(max_workers=1) as pool:  # Keep two independent PostgreSQL connections.
        ReservationRepository(holder).lock_field_family(BASKETBALL_COURT_ID)  # Prevent the worker from reaching its conflict decision yet.
        event.listen(engine, "before_cursor_execute", observe_lock)  # Observe only after the holder has locked.
        try:  # Always release the holder before joining the worker.
            future = pool.submit(write)  # Start the blocked write on another thread.
            try:  # Even a failed assertion must release the real row lock.
                assert requested_lock.wait(timeout=10)  # Wait for an event instead of guessing a delay.
                clock[0] = now + timedelta(minutes=30)  # Expire the first hold and pass the short requested start.
            finally:  # Let the waiting writer proceed with the advanced clock.
                holder.rollback()  # A lock-only transaction has no data to commit.
            if scenario == "past_start":  # Time-based validation must run after the wait too.
                with pytest.raises(InvalidInputError):  # This was future at transaction start but past when the lock became available.
                    future.result(timeout=15)  # Propagate the real service's error.
            else:  # The formerly occupied interval became free while waiting.
                assert future.result(timeout=15)["status"] == "HELD"  # A stale pre-lock clock would incorrectly report a conflict.
        finally:  # Leave no synchronization hooks attached to the engine.
            event.remove(engine, "before_cursor_execute", observe_lock)  # Restore normal query execution.
