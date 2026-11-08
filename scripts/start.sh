#!/bin/sh
# Container start-up: migrate, seed, serve. Stops at the first error (set -e).
set -e

echo "Applying database migrations..."
alembic upgrade head

echo "Loading demo data..."
python -m scripts.seed

echo "Starting the API on port 8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log