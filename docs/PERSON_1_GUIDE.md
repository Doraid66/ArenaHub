# Person 1: booking engine and demo guide

Implementation branch: `dani/phase2-bookings`. Nothing was committed or pushed by the assistant.
The implementation starts from the existing integrated authentication/catalog checkout.
The attached handoffs provide the team agreement; they are distinct from the user's request
and from the instructor's assessment brief.

## What is implemented

- Player holds, owner-only lookup, and repeatable cancellation.
- Configurable hold lifetime, ten minutes by default, and immediate effective expiry.
- One conflict engine for holds, manager blocks, and advisory availability.
- Half-open UTC intervals: `[08:00, 09:00)` and `[09:00, 10:00)` can coexist.
- Whole-field/child protection, while separate children remain independently bookable.
- A PostgreSQL root-row lock covering the conflict check and capacity change.
- Per-user/per-operation retry keys, canonical payload hashes, and durable response receipts.
- Migration `0003` after `0002`, HTTP/service tests, and real PostgreSQL races.

Payments and a transition into CONFIRMED remain deferred. The engine understands existing
CONFIRMED rows as occupancy, but no payment or fake confirmation endpoint was added.

## Run it on this Windows machine

The local virtual environment uses Python 3.12. The ignored `.env` contains generated local
database/JWT/seed credentials. Keep that file private; the two seed password entries are the
passwords to type into the testing page. The database listens on host port **5433**.

Another project already occupies port 8000. This checkout therefore has an ignored local
override at `.venv/demo-compose.yml` that publishes ArenaHub on **8001**:

```powershell
docker compose -f docker-compose.yml -f .venv/demo-compose.yml up --build -d --wait
```

Open [the testing page](http://localhost:8001) or [Swagger UI](http://localhost:8001/docs).
All frontend API calls use the same origin, so the alternate port requires no frontend edits.

If recreating the override after deleting `.venv`, its complete contents are:

```yaml
services:
  api:
    ports: !override
      - "8001:8000"
```

On another machine with port 8000 free, the existing `docker compose up --build -d --wait`
command works without that override. Follow the main README to create the environment first.
The new `.gitattributes` keeps `.sh` files as LF on Windows so Linux can execute `scripts/start.sh`.
If an existing checkout still has CRLF, normalize that file before rebuilding; no script logic changed.

Demo logins:

| Email | Password entry in `.env` | Role |
| --- | --- | --- |
| `player1@arenahub.test` | `SEED_PLAYER_PASSWORD` | Player |
| `player2@arenahub.test` | `SEED_PLAYER_PASSWORD` | Another player |
| `manager@arenahub.test` | `SEED_MANAGER_PASSWORD` | Manager of the demo centre |

Run checks from the repository root:

```powershell
.\.venv\Scripts\python.exe -m scripts.export_openapi --check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m scripts.concurrency_demo
git diff --check
```

The test suite recreates its separate `arenahub_test` database. The race demo uses the configured
development database, reports committed occupancy, and removes only its own newly created
reservations/receipts. Use a fresh future slot if the chosen demo date is already occupied.
The race script calls the real service with seeded trusted Principals; it does not claim to test
network concurrency or JWT verification. The HTTP tests and live Docker checks cover those
HTTP/authentication boundaries separately.

## Five-minute rehearsal

1. Log in as player 1. Pick tomorrow's 20:00–21:00 slot on 7v7 A. Check availability and place a hold.
2. Check again: A and its whole field are unavailable, while 7v7 B remains available.
3. Copy the booking ID. Log in as player 2. Reading or cancelling that booking returns 404.
4. Try the same field/time with player 2: 409 `slot_unavailable`. Run the terminal race script.
5. As manager, block an unused standalone field/time. A player or wrong-facility manager gets 403.
6. Return to player 1 and cancel the original hold. Repeat cancellation: both return 204.
7. For expiry, add `HOLD_MINUTES=1` to your local `.env`, then recreate the API container
   using the Compose command above. A new hold becomes EXPIRED after one minute and frees the slot.
   Existing holds retain the deadline they were created with. Remove the setting and recreate the
   API afterward if you want the normal ten-minute lifetime back.
8. Place another hold, restart only the API, and fetch the same ID to show persistence:

```powershell
docker compose -f docker-compose.yml -f .venv/demo-compose.yml restart api
```

The existing shared `docs/DEMO.md` is still useful, but its pre-integration status labels are stale.
This guide records Person 1's completed integration without rewriting Person 3's walkthrough.

## Explain the code in this order

| File | Explanation to give |
| --- | --- |
| `app/bookings/schemas.py` | The body accepts only start/end. Owner, status, and expiry come from the server. |
| `app/bookings/routes.py` | HTTP validation and translation only. Synchronous handlers delegate to the service. |
| `app/reservations/rules.py` | Offset normalization, interval validation, effective expiry, and request hashing. |
| `app/reservations/service.py` | Use-case decisions, owner/manager checks, transaction boundaries, and retry orchestration. |
| `app/reservations/repository.py` | Parameterized SQL, family locks, the one conflict query, and receipt lookups. |
| `app/reservations/models.py` | Occupancy and receipt persistence, with foreign keys and legal-state checks. |
| `migrations/versions/0003_create_reservations_and_idempotency_records.py` | The ordered schema change, independent of future model edits. |
| `scripts/concurrency_demo.py` | Independent database connections, synchronized starts, persisted winners, and scoped cleanup. |

The comments explain executable lines, parameters, and closing expressions in the new Python
files. Read the surrounding block as well: understanding the transaction matters more than
memorizing individual syntax.

### Why lock the parent row?

Two callers can both see an empty reservation query. Locking that empty result protects nothing.
The catalog field row always exists. A whole field and each of its children choose the same root
row, so only one writer at a time can check/change that family's occupancy. Different children
still both succeed because the conflict predicate compares the requested child with only itself
and its parent. The lock serializes the decision; it does not declare siblings spatially identical.

### Why READ COMMITTED?

After a writer gets the lock, its next SQL statement sees the previous writer's committed
reservation. PostgreSQL's default READ COMMITTED provides this new snapshot per statement.
The demo checks that isolation level. Changing it requires revisiting the retry/snapshot design.
Every production capacity change must continue to use the service's family-lock protocol;
direct administrative SQL can bypass this application-level invariant.

### Why clock_timestamp() instead of now()?

PostgreSQL `now()` means transaction start. Token/user lookups may have started that transaction
before a long lock wait. `clock_timestamp()` obtains current database time after acquiring the
lock, so newly elapsed holds release space and a start that passed while waiting is rejected.
The tests inject advancing time around a controlled lock wait without waiting ten minutes.

### Why no db.begin() block?

SQLAlchemy starts a transaction automatically on the first auth/catalog query. Blindly calling
`db.begin()` again would fail. The write service deliberately owns that same request transaction:
it commits once on success and rolls back on any failure. Repositories and facades never commit
independently. Pass it a dedicated request/use-case session, not an unrelated batch of pending work.

### How does a duplicate request work?

1. Normalize timestamps and hash field/start/end. Look up user + operation + key.
2. If a completed receipt exists, compare hashes and return its original response, or reject a
   changed payload with 409 `idempotency_conflict`. Current manager rights are still checked.
3. Otherwise acquire the root-field lock and check the receipt again: a matching request may
   have completed while this caller waited.
4. Check future start and active conflicts. Flush the new reservation, then save its response
   receipt and commit both together.
5. If two different families race for one scoped key, the unique receipt constraint selects a
   winner. Roll back the loser's entire transaction, including its flushed reservation, then
   read the winner and replay or reject the changed payload. There is no orphan booking.

Only successful creates are cached in this phase; rejected validation, authorization, and capacity
attempts leave no receipt. There is no key-retention cleanup job yet. Reusing an old successful
key returns the old response even after cancellation/expiry: GET gives the resource's current state.

### Why does expiry need no worker?

The conflict query counts HELD only when `hold_expires_at > current database time`.
GET computes EXPIRED for elapsed holds even when the stored state is still HELD.
Cancelling an elapsed hold persists EXPIRED and returns 204; nothing can revive it.

### Why the custom booking route class?

The generated contract test exposed a framework method-header behavior: an unsupported verb on
the shared GET/DELETE resource advertised only GET. `BookingRoute` collects the methods on this
router's matching path and raises the existing HTTP error with the complete `Allow` header.
The shared error handler still builds the JSON body. This code performs routing, never SQL.

## Shared changes to tell teammates about

- `app/main.py`: one booking-router import and one registration.
- `tests/integration/test_contract.py`: add booking creation to the existing cross-field-rule set.
- `contracts/openapi.json`: regenerated with `python -m scripts.export_openapi`; never edited manually.
- `.gitattributes`: force LF for shell scripts, fixing Windows Docker startup.
- `docs/AI_LOG.md`: record the observed method-header failure and its correction.

No auth, manager, catalog, frontend, Dockerfile, Compose, migration-environment, or shared-test-fixture
logic was rewritten. The one startup shell file was normalized locally to LF, matching its existing
Git contents. The port override and credentials stay ignored/local.

## Verification record

The implementation was exercised against PostgreSQL 17, Python 3.12, and the project's existing
pinned dependencies on November 11, 2026:

| Check | Result |
| --- | --- |
| Complete PostgreSQL suite, including randomized Schemathesis conformance | **170 passed, 2 skipped**, three consecutive runs (23.65s, 22.71s, 21.76s) |
| Two skipped tests | Old "engine not merged" placeholders deliberately skip when the real engine exists |
| Real PostgreSQL terminal races | All eight scenarios passed; capacity races used different users and keys |
| Eight simultaneous contenders | One created booking, seven controlled 409 responses, one persisted row |
| Simultaneous duplicate delivery | Four successful matching responses, one reservation and one receipt |
| Same key across different families | Unique constraint selected one winner; loser returned idempotency conflict and left no orphan |
| Time advancing while a writer waits | Expired occupancy released; newly past start rejected, without sleeps |
| Fresh disposable database migration round trip | Empty → 0003 → 0002 → 0003 succeeded; temporary database removed afterward |
| Schema checks | `alembic check`: no differences; one head 0003; actual check names, unique constraint, and foreign keys inspected |
| Contract export | Up to date; generated from the integrated app |
| Docker startup | PostgreSQL and API healthy; alternate local API port 8001 |
| Live Docker HTTP rehearsal | Frontend files, health, real logins, fields, availability, holds, retry, ownership, blocks, and cancellation passed |
| Restart persistence | Same HELD booking and timestamps survived API restart and seed rerun |
| API log check | No tested passwords, JWT signing secret, live token, or tracebacks found |
| Python compilation / whitespace | Passed |
| Git base | Remote main still matched starting revision `05cf1e2`; no commits or pushes made |

The final test counts include 51 Person 1 tests. Expiry is verified through the real service and
database with an injected clock, including the exact deadline; the one-minute browser countdown
was not manually timed. The frontend was served and its API flows were exercised through live
HTTP, without claiming a manual browser visual inspection.

See `docs/PERSON_1_COMMITS.md` for the exact staged commit/push sequence.
