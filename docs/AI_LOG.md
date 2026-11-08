# AI collaboration log

Every teammate adds entries as they work, not at the end. The final report uses 3–5 of the
best examples: where the assistant was wrong, incomplete, or insecure, and how we fixed it.

Entry format:

- **Date / who / tool**
- **Prompt:** what we asked
- **AI output:** what it produced
- **Problem:** what was wrong, incomplete or risky
- **Fix:** what we changed, and why
- **Lesson:** what to check next time

---

## Phase 2 — Bootstrap (Person 3)

### 2026-11-07 — Front-end helper assigned to a read-only property
- **Tool:** Claude
- **Prompt:** Build a plain JavaScript test front end for login, availability, holds and blocks.
- **AI output:** A DOM helper that used `Object.assign(element, props)`, including `dataset`.
- **Problem:** `element.dataset` is read-only; in strict mode the assignment throws, so the
  bookings table never rendered after a successful hold. It only showed up when the page
  was exercised end to end in a browser.
- **Fix:** Copy `dataset` values into `element.dataset` separately. Re-ran the full flow,
  including a simulated server crash to confirm the retry reuses the same Idempotency-Key.
- **Lesson:** Click through the real page; reading the code didn't reveal this.

### 2026-11-07 — Alembic skipped the wrong missing modules
- **Tool:** Claude
- **Prompt:** Set up Alembic so `env.py` imports every team's model modules, skipping
  modules that don't exist yet on a branch.
- **AI output:** A loop that skipped a module when `ModuleNotFoundError.name` equalled the
  full module name (e.g. `app.catalog.models`).
- **Problem:** Python reports the *missing package* (`app.catalog`), not the full module
  name, so on a branch without that folder Alembic crashed instead of skipping it.
- **Fix:** Skip when the missing name is the module *or one of its parent packages*;
  re-raise any other missing import, so a teammate's broken import is still reported.
  Tested both cases.
- **Lesson:** Test "skip if missing" logic against the real failure, not the assumed one.

### 2026-11-07 — Outdated test dependency
- **Tool:** Claude
- **Prompt:** Pin compatible dependency versions for FastAPI, SQLAlchemy, Alembic and tests.
- **AI output:** Included `httpx` for FastAPI's test client.
- **Problem:** The current Starlette test client warns that `httpx` is deprecated in favour
  of `httpx2`.
- **Fix:** Replaced `httpx` with `httpx2` in `requirements-dev.txt` after seeing the warning
  in a test run.
- **Lesson:** Run the code after pinning versions; library advice goes stale quickly.

### 2026-11-07 — Placeholder migration broke Alembic
- **Tool:** Claude
- **Prompt:** Create the folder and file structure for Person 3's tasks.
- **AI output:** Created an empty `migrations/versions/0001_create_facilities_and_fields.py`.
- **Problem:** Alembic refuses to run if any file in `versions/` has no `revision` id.
- **Fix:** Deleted the placeholder; migrations are generated with
  `alembic revision --rev-id 0001`, which fills in the ids.
- **Lesson:** Don't create empty files where a tool expects a specific format.

### 2026-11-07 — Migration created a doubled constraint name
- **Tool:** Claude
- **Prompt:** Write migration 0001 for facilities and fields, matching the models exactly.
- **AI output:** A migration naming the check constraint `ck_fields_not_own_parent`.
- **Problem:** The shared naming convention added its own `ck_fields_` prefix on top, so the
  database got `ck_fields_ck_fields_not_own_parent`. `alembic check` did not catch it, since
  it doesn't compare check constraints.
- **Fix:** Wrapped the name in `op.f(...)` so it is used exactly as written; confirmed with
  `\d fields`.
- **Lesson:** "No differences detected" only covers what the tool compares. Inspect the
  real table when names matter.
---

## Proposal phase (September 2026)

- **Wrong deadline:** the assistant said the proposal was due Wednesday; it was Thursday,
  Sept 24. Checked against the course schedule.
- **Wrong data model:** its first data model assumed cinema-style seats, which did not fit
  time-slot field booking with overlapping intervals.
- **Misread source:** it claimed the Centre Multisports de Rosemère calendar "only shows
  availability"; rereading the site showed online booking exists more than 72 hours ahead.
- **Unsupported claims:** it inferred problems the source never stated (double-booking
  risk, staff time, teammates not paying the organizer back); we kept them only as risks.
- **Overconfident differentiation:** it framed divisible fields and split payment as
  unique; research showed Amilia (subdivided spaces) and Playtomic (split payment) already
  offer them.
- **AI-generated statistic:** Google's AI Overview claimed "30–40 indoor soccer centres in
  Quebec"; the cited La Presse article (2012) actually said 27.