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



## Phase 2 – Person 2 (November 10, 2026)

- **Who / tool:** Person 2 with Codex.
- **Prompt:**I am Person 2, responsible for authentication, authorization, and manager blocks in Phase 2. The project already has shared interfaces that my implementation must follow. Person 1’s engine will be available later. First, review the existing code and interfaces, identify dependencies, and organize a step-by-step implementation and testing plan.Once I read it and modify what needs modification, execute the plan, explain key design decisions, and clearly identify what can be tested now and what must wait for integration.
- **AI output:** Login, signed tokens, database memberships, and a manager facade that rejected blocks whose start time was already in the past.
- **My code and design review:** I reviewed the generated code and questioned whether the facade should check the current time before forwarding a request to the shared engine. This could prevent a valid retry from reaching the engine’s idempotency lookup once the original block’s start time had passed.
- **My test review:** I questioned whether the tests covered retries after time had advanced. The regression test `test_retry_can_reach_engine_after_original_block_start` reproduced the issue with `InvalidInputError`, showing that the validation order broke valid retries.
- **Fix:** Removed the facade’s future-start check so the shared engine could replay completed requests before applying time-dependent validation to new requests. Authorization, UTC normalization, interval ordering, and key validation remained in the facade. A real-engine integration test was added to check that new past blocks were still rejected.
- **Lesson:** Reviewing AI-generated code requires questioning both design decisions and test coverage. A validation rule can appear correct while breaking retries after time or state changes.
- **Verification:**The full PostgreSQL suite passed three consecutive runs (112 passed, 6 skipped). These results do not establish real reservation integration, which remains unverified until Person 1’s implementation is available.

### November 10, 2026 - Unicode email validation differed from OpenAPI

- **Tool:** Codex.
- **Prompt:** Set up PostgreSQL and verify the implementation against the real database.
- **AI output:** An email pattern using `\s` for whitespace, shared between the
  request model and its generated OpenAPI schema.
- **Problem:** A repeated Schemathesis run generated an email containing Unicode
  NEXT LINE (`U+0085`). Rust's runtime regex rejected it, but the OpenAPI regex
  validator accepted it, so schema-valid input returned 422. A direct schema check
  confirmed the mismatch before the fix.
- **Fix:** Explicitly excluded `\u0085` in the pattern, added
  `test_email_whitespace_rejection_matches_the_published_contract`, regenerated the
  contract, and ran the full PostgreSQL suite successfully three times.
- **Lesson:** Identical regex text can behave differently in different regex engines.
  Repeat randomized conformance checks and compare runtime and contract validation
  against the exact failing input.



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

## Person 1 booking implementation (November 11, 2026)

**Starting point supplied by Person 1:** Before implementation began, Person 1 wrote and
provided `ArenaHub_Person1_Skeleton.zip`, alongside the team handoffs and course lectures.
The skeleton already defined the proposed models, booking schemas/routes, service and repository
interfaces, migration stub, and test/demo placeholders. Codex reviewed that starting point,
retained its useful structure, and completed or revised the unfinished implementation and tests.

### Booking resource method headers exposed by contract testing

- **Tool:** Codex.
- **Prompt:** Implement Person 1's booking engine using the shared handoff, lecture references,
  and skeleton, add explanatory inline comments, verify it, and leave changes uncommitted/unpushed.
- **AI output:** Separate ordinary FastAPI GET and DELETE handlers for `/bookings/{booking_id}`,
  plus shared-engine hold creation, ownership, expiry, transactions, and retry receipts.
- **Observed problem:** The first integrated PostgreSQL suite reported 118 passes, two obsolete
  placeholder skips, and one Schemathesis failure. `OPTIONS /bookings/{id}` correctly returned
  405 but advertised only `Allow: GET`, omitting the documented DELETE method.
- **Correction:** Add a booking-local APIRoute subclass that gathers all supported methods for
  the matching path before raising the existing shared HTTP error. The first correction looked
  through `app.routes`, but this installed FastAPI wraps included routers, so the focused test
  still failed. Inspecting the installed routing implementation showed why; reading the booking
  router's own routes fixed the header. A dedicated regression now asserts GET and DELETE.
- **Verification:** The complete integrated suite then passed. Separate PostgreSQL races also
  verified occupancy, same-key replay, and unique-constraint rollback without orphan bookings.
- **Lesson:** A plausible endpoint implementation can still violate HTTP contract details.
  Keep the generated conformance test active, reproduce its actual failure, and inspect the
  installed framework behavior instead of assuming its route structure.

### Windows checkout prevented the Linux startup script from running

- **Tool:** Codex.
- **Prompt:** Verify the implementation through the project's real Docker demo path.
- **AI output:** A successful image build followed by an attempted API container startup.
- **Observed problem:** After moving to a free local port, the API exited with
  `scripts/start.sh: 3: set: Illegal option -`. The tracked script used LF, but its Windows
  working copy had CRLF. Python/HTTP tests had not exercised Linux shell parsing.
- **Correction:** Add `*.sh text eol=lf` to `.gitattributes` and normalize the working copy to
  the already-tracked LF contents. No startup script logic or Dockerfile change was needed.
- **Verification:** Rebuilding produced a healthy Docker API; live HTTP calls verified the
  integrated booking workflow. The unrelated application occupying port 8000 stayed running;
  ArenaHub used an ignored local Compose override on port 8001.
- **Lesson:** Passing application tests does not verify the deployment entry point. Rehearse
  the actual container startup on the machine used for the demo.

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
