"""Test-only SQLite fixtures for checking auth HTTP behavior without Docker.

These never replace production persistence or prove PostgreSQL migration/concurrency
correctness. The full suite and test_postgres.py still use the shared PostgreSQL setup.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.demo_accounts import (
    DEMO_MANAGER_EMAIL, DEMO_MANAGER_ID,
    DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_1_ID, DEMO_PLAYER_2_EMAIL, DEMO_PLAYER_2_ID,
)
from app.auth.models import ManagerFacility, User
from app.auth.security import hash_password
from app.catalog.demo_data import DEMO_FACILITY_ID, FACILITIES, FIELDS
from app.catalog.models import Facility, Field
from app.core.database import Base, get_db
from app.main import app

TEST_PLAYER_PASSWORD = "test-only-player-passphrase"
TEST_MANAGER_PASSWORD = "test-only-manager-passphrase"


@pytest.fixture(scope="module")
def offline_hashes():
    return hash_password(TEST_PLAYER_PASSWORD), hash_password(TEST_MANAGER_PASSWORD)


@pytest.fixture
def isolated_db(offline_hashes):
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine, tables=[
        Facility.__table__, Field.__table__, User.__table__, ManagerFacility.__table__,
    ])
    with Session(engine, expire_on_commit=False) as db:
        player_hash, manager_hash = offline_hashes
        db.add_all([Facility(**row) for row in FACILITIES])
        db.add_all([
            User(id=DEMO_PLAYER_1_ID, email=DEMO_PLAYER_1_EMAIL, password_hash=player_hash),
            User(id=DEMO_PLAYER_2_ID, email=DEMO_PLAYER_2_EMAIL, password_hash=player_hash),
            User(id=DEMO_MANAGER_ID, email=DEMO_MANAGER_EMAIL, password_hash=manager_hash),
        ])
        db.flush()
        db.add_all([Field(**row) for row in FIELDS])
        db.add(ManagerFacility(user_id=DEMO_MANAGER_ID, facility_id=DEMO_FACILITY_ID))
        db.commit()
        yield db
    engine.dispose()


@pytest.fixture
def isolated_client(isolated_db):
    previous = dict(app.dependency_overrides)

    def database_override():
        yield isolated_db

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = database_override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
