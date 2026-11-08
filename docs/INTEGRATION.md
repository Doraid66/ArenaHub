# Integration checklist

How the three Phase 2 branches come together before the November 12 milestone.

**Timeline:** merge each branch as soon as its foundation works (don't wait for "finished");
all real implementations on `main` by **November 10**; **November 11** reserved for the
end-to-end demo rehearsal and concurrency checks.

## Merge order

| Order | Branch | Why this order |
|---|---|---|
| 1 | `phase2/security` (Person 2) | Real login and `users` (migration 0002), which Person 1's 0003 builds on |
| 2 | `phase2/bookings` (Person 1) | Reservation engine, bookings, idempotency (migration 0003) |
| 3 | Integration commit (Person 3) | Register routers, connect availability to the real engine, re-export the contract |

If Person 1 is ready first, they can merge first **only if** their migration 0003 still
says `down_revision = "0002"` and 0002 is already on `main`; otherwise wait.

## Before opening a pull request (everyone)

```bash
git fetch origin
git merge origin/main                 # bring your branch up to date; fix conflicts here
docker compose up -d db
python -m scripts.export_openapi      # if you changed or added any route
python -m pytest                      # everything passes, not only your tests
alembic heads                         # exactly ONE head
```

- [ ] Your migration has the agreed fixed ID and `down_revision`
      (`0002` → `"0001"`, `0003` → `"0002"`); `alembic heads` shows a single head.
- [ ] You only changed files you own (see the README's project layout). Need a change in
      someone else's file? Ask them, or note it in the PR.
- [ ] Time inputs use `UtcTimestamp` from `app/core/timestamps.py`.
- [ ] Errors are raised with the classes in `app/core/errors.py`, never built by hand.
- [ ] Database routes are plain `def`; services commit or roll back themselves.
- [ ] No secrets, tokens or passwords in code or logs; new settings added to `.env.example`.
- [ ] `contracts/openapi.json` re-exported and committed if any route changed.
- [ ] At least one entry added to `docs/AI_LOG.md`.
- [ ] PR description says what's done, how to test it, and what's left.

## 1. Merge Person 2 (`phase2/security`)

Expected in the PR:
- `app/core/principal.py`: the PLACEHOLDER bodies replaced, names and signatures unchanged.
- `app/auth/` (login, `/auth/me`, users, memberships), `app/manager/` (block route and service).
- `migrations/versions/0002_...py` with `down_revision = "0001"`.
- `app/auth/seed.py` with `seed_accounts(db)`: no commit inside, safe to run twice, passwords
  from `get_settings()`, demo manager linked to `DEMO_FACILITY_ID`.

After merging, Person 3:
- [ ] Register the routers in `app/main.py` (uncomment the `auth_router` and
      `manager_router` lines, adjusting module names if needed).
- [ ] If membership models live in `app.manager.models`, add it to `MODEL_MODULES` in
      `migrations/env.py`.
- [ ] Fresh start: `docker compose down -v && docker compose up --build -d`; the logs show
      `0001 → 0002` and `accounts: loaded`.
- [ ] Log in through the test client with each demo account.

## 2. Merge Person 1 (`phase2/bookings`)

Expected in the PR:
- `app/reservations/service.py` with `ReservationService(db)`, `is_available(field_id, start, end)`
  and `create_block(...)`; `app/bookings/` routes and service.
- `migrations/versions/0003_...py` with `down_revision = "0002"`.
- `scripts/concurrency_demo.py` running against real PostgreSQL with independent connections.

After merging, Person 3:
- [ ] Register `bookings_router` in `app/main.py`.
- [ ] In `app/catalog/routes.py`, replace the request-time import in
      `get_availability_checker` with a normal import at the top of the file:
      `from app.reservations.service import ReservationService`, and return
      `ReservationService(db)` directly. The 503 fallback and its test are no longer needed
      (the test already skips itself once `app.reservations` exists; delete it).
- [ ] In `tests/integration/test_contract.py`, add `"POST /fields/{field_id}/bookings"` and
      `"POST /fields/{field_id}/blocks"` to `CROSS_FIELD_RULES`.

## 3. Integration commit (Person 3)

```bash
git checkout main && git pull origin main
git checkout -b phase2/integration
python -m scripts.export_openapi       # now includes auth, bookings and blocks
python -m pytest                       # run it 2-3 times (Schemathesis is random)
```

- [ ] `contracts/openapi.json` lists every route: health, auth, fields, availability,
      bookings, blocks.
- [ ] README status table and `docs/DEMO.md` status column updated.
- [ ] PR merged into `main`.

## 4. End-to-end checks (November 11)

Run these on `main`, on a fresh start, and tick each one:

```bash
docker compose down -v
docker compose up --build -d
docker compose logs api | grep -v request
alembic history                        # 0001 -> 0002 -> 0003, nothing else
alembic check                          # "No new upgrade operations detected."
python -m pytest                       # all pass, 3 runs in a row
```

- [ ] Migrations run in order on an empty database; one head; models and database match.
- [ ] Seed runs twice without duplicates (`docker compose restart api`, then count rows).
- [ ] The whole test suite passes three runs in a row.
- [ ] Person 1's race script against real PostgreSQL: same field, partial overlap, full
      field vs sub-field (both directions), block vs booking all give exactly one winner;
      two different sub-fields both succeed; adjacent intervals both succeed.
- [ ] The full `docs/DEMO.md` walkthrough works through the test client, in order, timed.
- [ ] Data survives `docker compose restart api`.
- [ ] Logs contain no passwords, tokens or hashes:
      `docker compose logs api | grep -iE "password|bearer|eyJ|argon2"` prints nothing.
- [ ] Every teammate has commits under their own GitHub account (`git shortlog -sn`).
- [ ] Each teammate can explain every part, including the locking and idempotency logic.

## If something goes wrong

- **"Multiple heads" from Alembic:** two migrations have the same `down_revision`. Fix the
  `down_revision` in the later one; don't create an Alembic merge migration.
- **Conflict in `app/main.py`:** Person 3 owns it. Keep everyone's router lines and resolve
  in favour of registering all routers.
- **Conflict in `requirements.txt`:** keep both additions, re-install, run the full suite.
- **Drift test fails:** `python -m scripts.export_openapi`, commit `contracts/openapi.json`.
- **Contract test fails on a new route:** read the Schemathesis message; it includes a
  `curl` command reproducing the exact request. Fix the route (or its documented
  responses), not the test.