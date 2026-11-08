# Milestone demo — November 12

The walkthrough for the milestone demo, in order. Every step lists who owns it, whether it
works today, and the exact actions and expected results. Rehearse it end to end at least
once on November 11, on a fresh start, with a timer.

Every founder must be able to explain every step: the instructor may ask anyone about any part.

## Status at a glance

| # | Step | Owner | Status |
|---|---|---|---|
| 0 | Clean start, health checks | Person 3 | Ready |
| 1 | Login | Person 2 | Needs Person 2 |
| 2 | Fields and availability | Person 3 + Person 1 | Fields ready; availability needs Person 1's engine |
| 3 | HELD booking | Person 1 | Needs Person 1 |
| 4 | Owner-only access | Person 1 + Person 2 | Needs Persons 1 and 2 |
| 5 | Rejected competing booking (UI + race script) | Person 1 | Needs Person 1 |
| 6 | Full field vs sub-field, independent sub-fields | Person 1 | Needs Person 1 |
| 7 | Manager block (allowed and refused) | Person 2 + Person 1 | Needs Persons 1 and 2 |
| 8 | Cancellation and expiry release the slot | Person 1 | Needs Person 1 |
| 9 | Persistence after an API restart | Person 3 | Ready (re-check after integration) |
| 10 | Contract, conformance check, errors, logs | Person 3 | Ready |

Update the Status column as each part is merged.

## Before the demo

- Docker Desktop running, `.env` filled in (`cp .env.example .env`), virtual environment active.
- Fresh start so the demo data is predictable:

  ```bash
  docker compose down -v
  docker compose up --build -d
  docker compose ps            # both containers (healthy)
  ```

- Open in the browser: http://localhost:8000 (test client) and http://localhost:8000/docs.
- Keep a terminal open in the project folder for steps 5, 9 and 10.
- Demo accounts (seeded by Person 2; confirm the exact emails), passwords from `.env`:
  - `player1@arenahub.test` and `player2@arenahub.test`: `SEED_PLAYER_PASSWORD`
  - `manager@arenahub.test`: `SEED_MANAGER_PASSWORD`, manages the **ArenaHub Demo Centre** only
- Demo slot: choose a date in the future, e.g. tomorrow 20:00–21:30. Use the same slot
  throughout unless a step says otherwise.
- Optional, for step 8: set `HOLD_MINUTES=1` in `.env` before starting, so a hold expires
  during the demo instead of after 10 minutes (Person 1's engine must read
  `get_settings().hold_minutes`).

## 0. Clean start and health (Person 3)

1. Show `docker compose logs api`: migrations `0001 → 0002 → 0003` applied in order, then
   `Demo data ready.`, then the server starting.
2. Open http://localhost:8000/health/ready → `{"status":"ready"}`.

**Say:** one command starts PostgreSQL and the API; migrations run before the API serves;
the seed is safe to run on every start.

## 1. Login (Person 2)

1. In the test client, log in with a **wrong** password → `401 unauthenticated` (generic
   message, doesn't say whether the email exists).
2. Log in as `player1` → "Logged in", header shows the email, fields load automatically.

**Say:** signed JWT, 30 minutes; identity comes only from the token; passwords hashed.

## 2. Fields and availability (Person 3, engine by Person 1)

1. Open the field list: fields grouped by facility, with the three 7v7 fields indented under
   **Soccer Field (11v11)**.
2. Choose **Soccer Field - 7v7 A** and the demo slot → **Check availability** → *Available*,
   with the times shown in local time and UTC.

**Say:** availability is advisory; it asks the same engine the booking uses, so they can't
disagree. Times must include an offset and are converted to UTC at the API boundary.

## 3. HELD booking (Person 1)

1. **Place hold** on 7v7 A → *Hold placed: HELD*, with a countdown to expiry.
2. **Check availability** again → *Not available*.

**Say:** a milestone booking is a 10-minute HOLD, never CONFIRMED (payment comes in the
final phase). The request carried an `Idempotency-Key`.

## 4. Owner-only access (Persons 1 and 2)

1. Copy the booking ID (it stays in the lookup box after logging out).
2. **Log out**, log in as `player2`, **Get booking** → `404 not_found`.
3. Cancelling another player's booking also returns `404`: show Person 2's cross-user test
   (the test client only offers Cancel for your own bookings).

**Say:** 404, not 403, so other users can't even learn the booking exists. The ownership
check is in the booking service, not only in the route.

## 5. Rejected competing booking (Person 1)

1. As `player2`, **Place hold** on 7v7 A for the same slot → `409 slot_unavailable`.
2. Run the race script in the terminal (exact command from Person 1):

   ```bash
   python -m scripts.concurrency_demo
   ```

   Expected: many simultaneous requests from different users for the same space; exactly
   **one** succeeds and the database shows a single active reservation.

**Say:** every capacity-changing write locks the same parent-field row in PostgreSQL, then
checks for conflicts and inserts in one transaction (pessimistic locking).

## 6. Full field vs sub-field, independent sub-fields (Person 1)

1. As `player2`, try **Soccer Field (11v11)** for the demo slot → `409` (sub-field A is held).
2. As `player2`, try **Soccer Field - 7v7 B** for the same slot → `201 HELD`: different
   sub-fields don't conflict.
3. Show the corresponding cases in the race script output (parent vs child, child vs parent,
   two independent children both succeeding).

**Say:** the full field conflicts with each of its sub-fields; sub-fields don't conflict with
each other; adjacent times (e.g. 20:00–21:00 and 21:00–22:00) are allowed.

## 7. Manager block (Persons 2 and 1)

1. As `player1`, **Create block** on the **Basketball Court** → `403 forbidden` (not a manager).
2. Log in as `manager`; the page shows the facilities they manage. **Create block** on the
   **Basketball Court**, demo slot → `201 ACTIVE`.
3. Block **Riverside Sports Complex › Soccer Field (7v7)** → `403` (another facility).
4. Block **7v7 A** for the demo slot → `409` (player1's hold is still there).
5. Log in as `player1`, hold the **Basketball Court** for the demo slot → `409` (blocked).

**Say:** manager rights come from the database (`manager_facilities`), never from the token
or the request; blocks use the same conflict engine as bookings.

## 8. Cancellation and expiry release the slot (Person 1)

1. As `player1`, **Cancel** the 7v7 A hold → `204`; **Refresh** shows `CANCELLED`.
2. **Check availability** for 7v7 A → *Available* again; cancelling again still returns `204`.
3. Expiry: with `HOLD_MINUTES=1`, place a hold, wait for the countdown, press **Refresh**
   → `EXPIRED`, and availability is back. (Otherwise show the expiry tests.)

**Say:** an expired hold stops occupying space immediately, even without a cleanup job, and
is never revived.

## 9. Persistence after an API restart (Person 3)

1. Note a booking ID that is still `HELD` (or the manager's block).
2. Restart only the API:

   ```bash
   docker compose restart api
   ```

3. In the same browser tab (don't reload it), press **Refresh** on that booking → still
   there, same status. The login also still works: the token is signed with the secret from
   `.env`, not stored in the API's memory.

**Say:** data lives in PostgreSQL in a Docker volume; the seed on restart updates the demo
data without duplicating it.

## 10. Contract, conformance, errors and logs (Person 3)

1. Show `contracts/openapi.json` in the repository and http://localhost:8000/docs.
2. Run the conformance check:

   ```bash
   docker compose up -d db
   python -m pytest tests/integration/test_contract.py -v
   ```

   **Say:** Schemathesis generates hundreds of valid and invalid requests from the contract
   and checks every response against it; it found a real 500 in our availability endpoint
   (a year-1 timestamp), now fixed with a regression test.
3. Error handling: in the test client, check availability with the end before the start →
   `422 invalid_input`, no stack trace.
4. Correlation ID: copy a `Request ID` from the request log, then:

   ```bash
   docker compose logs api | grep <request-id>
   ```

   → the JSON log line for that exact request.

## If something goes wrong

- Containers not healthy: `docker compose logs api` and `docker compose logs db`.
- Unexpected data: `docker compose down -v && docker compose up --build -d` resets everything.
- A step fails during the demo: say what should happen, show the relevant test passing, move on.