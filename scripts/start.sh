#!/bin/sh
# Container start-up: migrate, seed, serve. Stops at the first error (set -e).
set -e # Exit immediately if any command fails.

echo "Applying database migrations..." # Tell the user what is happening.
alembic upgrade head # Bring the database schema up to date.

echo "Loading demo data..." # Tell the user what is happening.
python -m scripts.seed # Insert or refresh the demo rows; safe to repeat.

echo "Starting the API on port 8000..." # Tell the user what is happening.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log # Replace this shell with the server; listen on all interfaces; app logs its own requests.
