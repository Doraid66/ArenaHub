"""Shared test setup.

Tests run against a SEPARATE database (your normal database name + "_test", e.g.
"arenahub_test"), which is deleted and rebuilt from the migrations at the start of
every run. Your development data is never touched.

The database server must be running:  docker compose up -d db
"""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime

# 1. Point the app at the test database BEFORE any app module creates the engine.
from sqlalchemy.engine import make_url

from app.core.config import Settings

_dev_url = make_url(Settings().database_url)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _dev_url.set(
    database=f"{_dev_url.database}_test"
).render_as_string(hide_password=False)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.catalog.routes import get_availability_checker  # noqa: E402
from app.core.principal import Principal, get_current_principal  # noqa: E402
from app.main import app  # noqa: E402


def _recreate_test_database() -> None:
    """Drop and create the test database, connected to the server's default 'postgres' db."""
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    """Once per test run: fresh database, all migrations, demo data."""
    _recreate_test_database()
    command.upgrade(Config("alembic.ini"), "head")  # also proves the migrations work
    from scripts.seed import main as seed

    seed()


# 2. Stand-ins for teammates' parts (used only in tests).

@dataclass
class FakeAvailability:
    """Records what it was asked and returns a fixed answer."""

    answer: bool = True
    calls: list[tuple[uuid.UUID, datetime, datetime]] = field(default_factory=list)

    def is_available(self, field_id: uuid.UUID, start: datetime, end: datetime) -> bool:
        self.calls.append((field_id, start, end))
        return self.answer


@pytest.fixture
def fake_availability() -> FakeAvailability:
    return FakeAvailability()


@pytest.fixture
def anon_client() -> Iterator[TestClient]:
    """A client with no login."""
    yield TestClient(app)


@pytest.fixture
def client(fake_availability: FakeAvailability) -> Iterator[TestClient]:
    """A logged-in client (stand-in user) whose availability answers come from the fake."""
    app.dependency_overrides[get_current_principal] = lambda: Principal(user_id=uuid.uuid4())
    app.dependency_overrides[get_availability_checker] = lambda: fake_availability
    yield TestClient(app)
    app.dependency_overrides.clear()