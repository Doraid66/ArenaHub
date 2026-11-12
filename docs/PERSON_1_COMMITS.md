# Commit and push Person 1's work in parts

These commands are instructions for you to run. The assistant did not stage, commit, push,
merge, or open a PR. Run them in PowerShell from the ArenaHub repository root. All four groups
are ordinary commits on **one branch**, `dani/phase2-bookings`.

## Check your branch and authorship

```powershell
git branch --show-current
git status --short
git config user.name
git config user.email
```

The branch should be `dani/phase2-bookings`. Confirm the displayed name/email are yours before
committing. If needed, set them locally with your actual values:

```powershell
git config user.name "Your Name"
git config user.email "your-github-email@example.com"
```

## Part 1: reservation persistence and service

This introduces the shared engine and migration, plus its direct use-case tests.

```powershell
git add app/reservations migrations/versions/0003_create_reservations_and_idempotency_records.py
git add tests/bookings/__init__.py tests/bookings/conftest.py tests/bookings/test_service.py
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m "Add reservation engine with family locks and durable retry receipts"
```

## Part 2: booking HTTP interface and contract

This connects player creation/read/cancel to the existing app, with real HTTP tests and the
updated machine-readable API. It also includes the observed Allow-header regression fix.

```powershell
git add app/bookings app/main.py contracts/openapi.json
git add tests/integration/test_contract.py tests/bookings/test_routes.py
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m "Expose owner-authorized booking endpoints and publish their contract"
```

## Part 3: PostgreSQL concurrency proof

This adds the executable demo and races, including cross-family duplicate-key rollback and
time advancing while waiting for a family lock.

```powershell
git add scripts/concurrency_demo.py tests/bookings/test_concurrency.py
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m "Demonstrate PostgreSQL booking races and test lock-wait edge cases"
```

## Part 4: Windows startup compatibility and handoff

The Git attribute preserves Linux shell-script endings in Windows checkouts. The guide explains
setup, the demo, important implementation choices, and the validation evidence.

```powershell
git add .gitattributes scripts/start.sh docs/PERSON_1_GUIDE.md docs/PERSON_1_COMMITS.md docs/AI_LOG.md
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m "Document Person 1 demo and preserve shell script line endings"
```

## Verify and publish the branch

Run the checks before pushing the completed branch:

```powershell
.\.venv\Scripts\python.exe -m scripts.export_openapi --check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m scripts.concurrency_demo
git status --short
git log -4 --oneline
git push -u origin dani/phase2-bookings
```

After that, ordinary `git push` publishes later commits on this branch. If you want to push
each part separately, run the initial `git push -u origin dani/phase2-bookings` after Part 1
and `git push` after each later part. Parts 1–3 build on each other; wait for the completed
branch before requesting integration review. Do not manufacture separate dates for these commits.

If teammates update `main` before you publish, fetch and inspect their changes first, integrate
them on your branch, then rerun the checks. Do not force-push or merge into main as part of these
instructions. The generated contract should always come from the final assembled application.

`.env`, `.venv/`, the local Compose override, extracted lecture text, caches, and credentials are
ignored and should never be included in these commits. Use the explicit paths above so each
commit contains only its stated task.
