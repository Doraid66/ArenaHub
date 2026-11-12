"""Run real PostgreSQL races: python -m scripts.concurrency_demo.

Calls the real service with seeded identities, using one database connection per worker.
Only rows created by this run are removed, after showing the final occupancy.
"""

import uuid  # Every attempt gets its own key unless testing duplicate delivery.
from concurrent.futures import ThreadPoolExecutor  # Workers execute on separate threads.
from dataclasses import dataclass  # Give each attempt and outcome a readable structure.
from datetime import datetime, timedelta, timezone  # Generate future intervals relative to this run.
from threading import Barrier  # Release all connected workers at the same time.

from sqlalchemy import delete, select, text, tuple_  # Inspect occupancy and remove only this demo's exact scoped receipts.

from app.auth.demo_accounts import DEMO_MANAGER_ID, DEMO_PLAYER_1_ID, DEMO_PLAYER_2_ID  # Existing seeded users, never invented foreign keys.
from app.catalog.demo_data import BASKETBALL_COURT_ID, FOOTBALL_FIELD_ID, FULL_SOCCER_FIELD_ID, SUB_FIELD_A_ID, SUB_FIELD_B_ID  # Shared stable catalog identifiers.
from app.catalog.repository import get_field  # Find root rows for cleanup locks.
from app.core.database import SessionLocal  # Each worker obtains an independent session.
from app.core.errors import IdempotencyConflictError, SlotUnavailableError  # These are the two expected race rejections.
from app.core.principal import Principal  # Trusted service callers still pass through owner/manager checks.
from app.reservations.models import IdempotencyRecord, Reservation  # Verify persisted rows as well as returned results.
from app.reservations.repository import ReservationRepository  # Cleanup obeys the same family lock protocol.
from app.reservations.service import ReservationService  # Exercise production transactions and conflict rules.


@dataclass(frozen=True)  # Attempts are fixed before workers start.
class Attempt:  # Explicit inputs make each race scenario easy to read.
    user_id: uuid.UUID  # A real seeded player or manager.
    field_id: uuid.UUID  # The requested surface.
    start: datetime  # Inclusive start.
    end: datetime  # Exclusive end.
    key: str  # Opaque idempotency key.
    kind: str = "BOOKING"  # Most scenarios place player holds.


@dataclass(frozen=True)  # Outcomes retain evidence from each independent connection.
class Outcome:  # Separate an expected rejection from an unexpected exception.
    status: int  # 201 for a successful create or replay; 409 for an expected conflict.
    body: dict  # The DTO or stable error code.
    backend_pid: int  # Distinct PostgreSQL backend PIDs prove separate connections.


def run_parallel_attempts(attempts: list[Attempt]) -> list[Outcome]:  # Also reused by the PostgreSQL race tests.
    barrier = Barrier(len(attempts))  # Every worker must connect before any may write.

    def worker(attempt: Attempt) -> Outcome:  # Each invocation owns its connection and transaction.
        with SessionLocal() as db:  # Never share SQLAlchemy sessions between threads.
            db.execute(text("SET LOCAL statement_timeout = '15s'"))  # Bound a broken demo instead of hanging indefinitely.
            backend_pid = db.scalar(select(text("pg_backend_pid()")))  # Open the connection before joining the barrier.
            isolation = db.scalar(text("SHOW transaction_isolation"))  # The locking design requires a fresh snapshot per statement.
            if isolation != "read committed":  # Fail clearly if the database configuration changed.
                raise RuntimeError("The concurrency demo requires PostgreSQL READ COMMITTED")  # Do not claim success under an untested isolation level.
            barrier.wait(timeout=20)  # Synchronize starts after all independent connections exist.
            service = ReservationService(db)  # Authentication-style reads have already autobegun the transaction.
            create = service.create_block if attempt.kind == "BLOCK" else service.create_hold  # Both use the same write boundary.
            try:  # Capacity and duplicate-payload conflicts are normal outcomes.
                body = create(Principal(attempt.user_id), attempt.field_id, attempt.start, attempt.end, attempt.key)  # Execute a real committed write.
                return Outcome(201, body, backend_pid)  # Success or exact replay.
            except (SlotUnavailableError, IdempotencyConflictError) as error:  # Let every unexpected failure fail the script/test.
                return Outcome(409, {"code": error.code}, backend_pid)  # Preserve which conflict occurred.

    with ThreadPoolExecutor(max_workers=len(attempts)) as pool:  # Enough workers to reach the barrier together.
        return list(pool.map(worker, attempts))  # Propagate unexpected thread exceptions to the caller.


def inspect_occupancy(outcomes: list[Outcome]) -> list[dict]:  # Verify the database, not merely response codes.
    ids = {uuid.UUID(result.body["id"]) for result in outcomes if result.status == 201}  # Replays deliberately collapse to one resource.
    with SessionLocal() as db:  # A fresh connection sees only committed rows.
        rows = db.scalars(select(Reservation).where(Reservation.id.in_(ids)))  # Inspect this race's successful resources only.
        return [{"id": str(row.id), "field_id": str(row.field_id), "kind": row.kind, "status": row.status} for row in rows]  # Enough detail to explain the winner.


def cleanup_attempts(attempts: list[Attempt]) -> None:  # This helper never deletes pre-existing bookings.
    scopes = {  # Include the whole namespace so another user's identical key text is never deleted.
        (attempt.user_id, "create_block" if attempt.kind == "BLOCK" else "create_hold", attempt.key)  # Same scope as the production unique constraint.
        for attempt in attempts  # Repeated deliveries collapse into one scope.
    }  # Cleanup addresses attempts, not an entire user's booking history.
    with SessionLocal() as db:  # Cleanup is itself a capacity-changing transaction.
        roots = {get_field(db, attempt.field_id).parent_field_id or attempt.field_id for attempt in attempts}  # Same stable lock targets as creation.
        repository = ReservationRepository(db)  # Reuse the production locking implementation.
        for root in sorted(roots, key=str):  # A fixed order prevents deadlocks when cleaning several families.
            repository.lock_field_family(root)  # Wait for any in-flight writer before deleting occupancy.
        receipts = list(db.scalars(select(IdempotencyRecord).where(  # Only exact caller/operation/key matches belong to this run.
            tuple_(IdempotencyRecord.user_id, IdempotencyRecord.operation, IdempotencyRecord.key).in_(scopes)  # Preserve identical key text in other namespaces.
        )))  # Read only completed receipts for the attempted requests.
        ids = {uuid.UUID(record.response_body["id"]) for record in receipts}  # Each receipt identifies the row actually created.
        db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.id.in_([record.id for record in receipts])))  # Remove just these replay receipts.
        db.execute(delete(Reservation).where(Reservation.id.in_(ids)))  # Remove just the demonstrated occupancy.
        db.commit()  # Release all cleanup locks together.


def main() -> None:  # This demo requires migrations and demo accounts to have been seeded.
    start = datetime.now(timezone.utc) + timedelta(days=90)  # No hard-coded calendar date becomes stale.
    end = start + timedelta(hours=1)  # Use one-hour intervals for visible comparisons.
    cases = [  # First and second attempt inputs, followed by expected successes.
        ("same field", BASKETBALL_COURT_ID, BASKETBALL_COURT_ID, start, start, "BOOKING", 1),  # Exactly one winner.
        ("partial overlap", BASKETBALL_COURT_ID, BASKETBALL_COURT_ID, start, start + timedelta(minutes=30), "BOOKING", 1),  # Unequal intervals still overlap.
        ("parent vs child", FULL_SOCCER_FIELD_ID, SUB_FIELD_A_ID, start, start, "BOOKING", 1),  # Full field occupies the child.
        ("child vs parent", SUB_FIELD_A_ID, FULL_SOCCER_FIELD_ID, start, start, "BOOKING", 1),  # Spatial protection works in both directions.
        ("independent children", SUB_FIELD_A_ID, SUB_FIELD_B_ID, start, start, "BOOKING", 2),  # Shared lock does not mean shared occupancy.
        ("adjacent intervals", FOOTBALL_FIELD_ID, FOOTBALL_FIELD_ID, start, end, "BOOKING", 2),  # Half-open endpoints may touch.
        ("block vs booking", SUB_FIELD_A_ID, FULL_SOCCER_FIELD_ID, start, start, "BLOCK", 1),  # The manager uses the real authorization guard.
    ]  # Each scenario is cleaned before the next one starts.
    for name, first_field, second_field, first_start, second_start, second_kind, expected in cases:  # Run all required spatial races.
        attempts = [  # Different callers and keys keep these races independent of retry protection.
            Attempt(DEMO_PLAYER_1_ID, first_field, first_start, first_start + timedelta(hours=1), str(uuid.uuid4())),  # Player's hold.
            Attempt(DEMO_MANAGER_ID if second_kind == "BLOCK" else DEMO_PLAYER_2_ID, second_field, second_start, second_start + timedelta(hours=1), str(uuid.uuid4()), second_kind),  # Competing hold or authorized block.
        ]  # Both attempts start together inside the helper.
        try:  # Always clean this run's rows, even if an assertion fails.
            outcomes = run_parallel_attempts(attempts)  # Real independent PostgreSQL transactions.
            successes = sum(result.status == 201 for result in outcomes)  # Count successful creates.
            occupancy = inspect_occupancy(outcomes)  # Read the committed result from a new connection.
            print(f"{name}: attempts=2, successes={successes}, rejections={2 - successes}, occupancy={len(occupancy)}")  # Easy-to-read demo summary.
            for row in occupancy:  # Show which surfaces and kinds survived.
                print(f"  {row}")  # No credentials, headers, or retry keys are printed.
            if successes != expected or len(occupancy) != expected or len({result.backend_pid for result in outcomes}) != 2:  # Validate capacity and separate connections.
                raise AssertionError(f"Unexpected result for {name}")  # Exit nonzero on a failed demonstration.
        finally:  # Leave an existing development database as we found it.
            cleanup_attempts(attempts)  # Only this scenario's receipts and reservations are removed.
    key = str(uuid.uuid4())  # Duplicate delivery is a separate test from capacity contention.
    attempts = [Attempt(DEMO_PLAYER_1_ID, BASKETBALL_COURT_ID, start, end, key)] * 2  # Same caller, operation, payload, and key.
    try:  # Inspect the duplicate-delivery result before cleanup.
        outcomes = run_parallel_attempts(attempts)  # Both requests may return success for the same resource.
        occupancy = inspect_occupancy(outcomes)  # Successful responses must still correspond to only one row.
        if any(result.status != 201 for result in outcomes) or len(occupancy) != 1 or outcomes[0].body != outcomes[1].body:  # Replayed response must match exactly.
            raise AssertionError("Duplicate delivery created an unexpected result")  # Fail loudly if retry protection broke.
        print("duplicate key: attempts=2, successes=2, rejections=0, occupancy=1 (same resource replayed)")  # Explain why two 201s are correct here.
    finally:  # Avoid leaving even the retry example behind.
        cleanup_attempts(attempts)  # Receipts identify the single created row.
    print("All PostgreSQL races passed; this run's demo rows were removed.")  # Final success marker for the terminal demo.


if __name__ == "__main__":  # Support the agreed python -m scripts.concurrency_demo command.
    main()  # Unexpected failures produce a nonzero exit status.
