# ArenaHub

ArenaHub is a back-end booking service for multi-sport facilities. Players browse fields,
hold a time slot, and (later) pay for it; facility managers block time for maintenance or
events. The service guarantees that a field is never double-booked, including a full field
versus its sub-fields.

SOEN 387 — Web-Based Enterprise Application Design, Concordia University, Fall 2026.

**Founders:** _(add team names)_

## Tech stack

- Python 3.12, FastAPI, Pydantic
- PostgreSQL 17, SQLAlchemy 2, Alembic (migrations)
- Docker Compose
- pytest, Schemathesis (OpenAPI conformance)
- Plain HTML/CSS/JavaScript test front end (served by FastAPI)

## Quick start (Docker)

Requirements: Docker Desktop running.

```bash
cp .env.example .env          # then edit .env with your own LOCAL values (see comments inside)
docker compose up --build     # add -d to run in the background
```

This starts PostgreSQL and the API, applies all migrations, loads demo data, and serves on
port 8000.

- Test front end: http://localhost:8000
- API docs (Swagger UI): http://localhost:8000/docs
- OpenAPI contract: http://localhost:8000/openapi.json
- Liveness: http://localhost:8000/health/live
- Readiness (checks the database): http://localhost:8000/health/ready

Stop with `docker compose down` (data is kept). `docker compose down -v` also deletes the
database volume for a completely fresh start.

## Local development (without the API container)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

docker compose up -d db                          # only the database
alembic upgrade head                             # apply migrations
python -m scripts.seed                           # load demo data (safe to run again)
uvicorn app.main:app --reload --no-access-log    # http://localhost:8000
```

Settings are read from `.env`. Variables exported in your shell take priority over `.env`.
Stop the `api` container first if it is running, since both use port 8000.

## Running the tests

```bash
docker compose up -d db
python -m pytest
```

Tests use a separate database (`arenahub_test`), rebuilt from the migrations and demo
data on every run; your development data is never touched. Useful fixtures in
`tests/conftest.py`: `client` (a logged-in stand-in user, with a fake availability
engine) and `anon_client` (no login).

## Demo data

`scripts/seed.py` loads fixed IDs from `app/catalog/demo_data.py`, so tests and seed
data can import them instead of copying strings:

| Constant | What it is |
|---|---|
| `DEMO_FACILITY_ID` | ArenaHub Demo Centre |
| `FULL_SOCCER_FIELD_ID` | Soccer Field (11v11): parent of the three 7v7 fields |
| `SUB_FIELD_A_ID`, `SUB_FIELD_B_ID`, `SUB_FIELD_C_ID` | 7v7 sub-fields of the full field |
| `BASKETBALL_COURT_ID`, `FOOTBALL_FIELD_ID` | Standalone fields |
| `OTHER_FACILITY_ID`, `OTHER_SOCCER_FIELD_ID` | A second facility, for "manager of another facility" tests |

Demo accounts are added by `app/auth/seed.py` (`seed_accounts(db)`, Person 2) once it exists.

## Project layout

| Path | Owner | Purpose |
|---|---|---|
| `app/main.py` | Person 3 | Creates the app, registers middleware, error handlers, routers and the front end |
| `app/core/` | Person 3 (except `principal.py`) | Settings, database session, error format, logging, health checks |
| `app/core/principal.py` | Person 2 | Current user (`Principal`) and manager-authorization helpers |
| `app/auth/`, `app/manager/` | Person 2 | Login, tokens, manager blocks |
| `app/bookings/`, `app/reservations/` | Person 1 | Holds, conflict engine, idempotency, concurrency |
| `app/catalog/` | Person 3 | Facilities, fields, availability, demo data |
| `frontend/` | Person 3 | Test front end |
| `contracts/` | Person 3 | Exported OpenAPI contract |
| `migrations/` | Each owner | Alembic migrations 0001 (P3), 0002 (P2), 0003 (P1) |
| `scripts/` | Person 3 | Start-up script, demo data seed |
| `tests/` | Each owner | Tests per module; shared fixtures in `tests/conftest.py` |
| `docs/AI_LOG.md` | Everyone | AI collaboration log |

## Team conventions

- **Errors:** raise the typed errors in `app/core/errors.py` (`NotFoundError`,
  `SlotUnavailableError`, ...). Every error is returned as
  `{"error": {"code": "...", "message": "..."}}`; callers never see a stack trace.
  Document a route's errors with `responses=error_responses(401, 404, ...)`.
- **Database:** every model uses the one `Base` from `app/core/database.py`. Routes get a
  session with `Depends(get_db)`, which never commits — services commit or roll back
  themselves. Routes that use the database are plain `def`, not `async def`.
- **Login:** protected routes take `principal: Principal = Depends(get_current_principal)`.
  The caller's identity always comes from the token, never from the request body.
- **Migrations:** always use a fixed revision id, in order:
  `alembic revision -m "short description" --rev-id 0002`
  and set `down_revision` to the previous id.
- **Logging:** use `logging.getLogger(__name__)`. Every log line is JSON and includes the
  request's correlation id (also returned in the `X-Request-ID` response header). Never log
  passwords, tokens or request bodies.
- **Secrets:** only in `.env` (ignored by Git). `.env.example` holds placeholders.
- **Git:** work on your own branch (`phase2/bookings`, `phase2/security`,
  `phase2/catalog-demo`), small commits under your own account.

## Status (milestone: November 12)

| Feature | Status |
|---|---|
| Project bootstrap: settings, database, error format, JSON logs + correlation id, health checks, Alembic, Docker Compose | Done |
| Facilities and fields (migration 0001, demo data), `GET /fields`, `GET /fields/{id}/availability`, test front end | Done (availability returns 503 until the reservation engine is merged) |
| Login, tokens, manager authorization, manager blocks | In progress (`app/core/principal.py` is a placeholder that rejects every request) |
| Booking holds, conflict engine, idempotency, concurrency test | In progress |
| Published OpenAPI contract + conformance check | Planned |
| Payments (simulated provider), email confirmation, split payment (v1.1) | Deferred to final phase |