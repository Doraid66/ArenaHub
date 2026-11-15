"""Shared test setup.

Tests run against a SEPARATE database (your normal database name + "_test", e.g.
"arenahub_test"), which is deleted and rebuilt from the migrations at the start of
every run. Your development data is never touched.

The database server must be running:  docker compose up -d db
"""

import os  # Read and set environment variables.
import uuid  # Type hints for IDs.
from collections.abc import Iterator  # Type for fixtures that yield.
from dataclasses import dataclass, field  # Build the fake availability checker.
from datetime import datetime  # Type hints for times.

# 1. Point the app at the test database BEFORE any app module creates the engine.
from sqlalchemy.engine import make_url  # Parse and edit database URLs.

from app.auth.demo_accounts import DEMO_PLAYER_1_ID  # The stand-in logged-in user.
from app.core.config import Settings  # Read the development database URL.

_dev_url = make_url(Settings().database_url)  # The normal development database URL.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _dev_url.set(  # Use an explicit test URL, or build one.
    database=f"{_dev_url.database}_test"  # Same server, database name plus "_test".
).render_as_string(hide_password=False)  # Keep the password so the URL still works.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL  # Make the app use the test database.

import pytest  # Test framework.  # noqa: E402
from alembic import command  # Run migrations.  # noqa: E402
from alembic.config import Config  # Load alembic.ini.  # noqa: E402
from fastapi.testclient import TestClient  # Call the API without a real server.  # noqa: E402
from sqlalchemy import create_engine, text  # Admin connection and raw SQL.  # noqa: E402

from app.catalog.routes import get_availability_checker  # Dependency replaced by a fake.  # noqa: E402
from app.core.principal import Principal, get_current_principal  # Dependency replaced by a stand-in login.  # noqa: E402
from app.main import app  # The application under test.  # noqa: E402


def _recreate_test_database() -> None:  # Start every run from an empty database.
    """Drop and create the test database, connected to the server's default 'postgres' db."""
    url = make_url(TEST_DATABASE_URL)  # Parse the test database URL.
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")  # DROP/CREATE DATABASE cannot run in a transaction.
    with admin.connect() as conn:  # Open one admin connection.
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))  # Remove the old test database, even if in use.
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))  # Create a fresh one.
    admin.dispose()  # Close the admin connections.


@pytest.fixture(scope="session", autouse=True)  # Runs once, automatically, before any test.
def test_database() -> None:  # Prepare the test database.
    """Once per test run: fresh database, all migrations, demo data."""
    _recreate_test_database()  # Empty database.
    command.upgrade(Config("alembic.ini"), "head")  # Also proves the migrations work.
    from scripts.seed import main as seed  # Imported late, after the database exists.

    seed()  # Load demo facilities, fields, and accounts.


# 2. Stand-ins for teammates' parts (used only in tests).

@dataclass  # Plain class that records calls.
class FakeAvailability:  # Replaces the real reservation engine in catalog tests.
    """Records what it was asked and returns a fixed answer."""

    answer: bool = True  # What the fake will answer.
    calls: list[tuple[uuid.UUID, datetime, datetime]] = field(default_factory=list)  # Every question asked, in order.

    def is_available(self, field_id: uuid.UUID, start: datetime, end: datetime) -> bool:  # Same method as the real engine.
        self.calls.append((field_id, start, end))  # Remember the question.
        return self.answer  # Give the preset answer.


@pytest.fixture  # New fake for each test.
def fake_availability() -> FakeAvailability:  # Provide the fake.
    return FakeAvailability()  # Starts out answering True.


@pytest.fixture  # New client for each test.
def anon_client() -> Iterator[TestClient]:  # A client that is not logged in.
    """A client with no login."""
    yield TestClient(app)  # Real login checks stay active.


@pytest.fixture  # New client for each test.
def client(fake_availability: FakeAvailability) -> Iterator[TestClient]:  # A logged-in client with a fake engine.
    """A logged-in client (stand-in user) whose availability answers come from the fake."""
    app.dependency_overrides[get_current_principal] = lambda: Principal(user_id=DEMO_PLAYER_1_ID)  # Always logged in as player 1.
    app.dependency_overrides[get_availability_checker] = lambda: fake_availability  # Availability comes from the fake.
    yield TestClient(app)  # Run the test.
    app.dependency_overrides.clear()  # Remove the stand-ins afterwards.
