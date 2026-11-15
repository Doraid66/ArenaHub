"""Test-only SQLite fixtures for checking auth HTTP behavior without Docker.

These never replace production persistence or prove PostgreSQL migration/concurrency
correctness. The full suite and test_postgres.py still use the shared PostgreSQL setup.
"""

import pytest  # Fixtures.
from fastapi.testclient import TestClient  # Call the API without a real server.
from sqlalchemy import create_engine, event  # Build a SQLite engine and hook its connections.
from sqlalchemy.orm import Session  # A database session.
from sqlalchemy.pool import StaticPool  # Share one in-memory connection.

from app.auth.demo_accounts import (  # Fixed demo IDs and emails.
    DEMO_MANAGER_EMAIL, DEMO_MANAGER_ID,  # The manager account.
    DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_1_ID, DEMO_PLAYER_2_EMAIL, DEMO_PLAYER_2_ID,  # The two player accounts.
)  # Finish the demo imports.
from app.auth.models import ManagerFacility, User  # Auth tables.
from app.auth.security import hash_password  # Hash the test passwords.
from app.catalog.demo_data import DEMO_FACILITY_ID, FACILITIES, FIELDS  # Fixed demo catalog rows.
from app.catalog.models import Facility, Field  # Catalog tables.
from app.core.database import Base, get_db  # Shared base and the session dependency.
from app.main import app  # The application under test.

TEST_PLAYER_PASSWORD = "test-only-player-passphrase"  # Password given to both test players.
TEST_MANAGER_PASSWORD = "test-only-manager-passphrase"  # Password given to the test manager.


@pytest.fixture(scope="module")  # Hash once per test file; hashing is slow.
def offline_hashes():  # Precompute the two password hashes.
    return hash_password(TEST_PLAYER_PASSWORD), hash_password(TEST_MANAGER_PASSWORD)  # Player hash, then manager hash.


@pytest.fixture  # New database for each test.
def isolated_db(offline_hashes):  # An in-memory SQLite database with demo data.
    engine = create_engine(  # Build the SQLite engine.
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,  # In memory, usable across threads, one shared connection.
    )  # Finish the engine.

    @event.listens_for(engine, "connect")  # Run on every new connection.
    def enable_foreign_keys(connection, record):  # SQLite ignores foreign keys by default.
        connection.execute("PRAGMA foreign_keys=ON")  # Turn enforcement on.

    Base.metadata.create_all(engine, tables=[  # Create only the tables these tests need.
        Facility.__table__, Field.__table__, User.__table__, ManagerFacility.__table__,  # Catalog and auth tables.
    ])  # Finish the table list.
    with Session(engine, expire_on_commit=False) as db:  # Open a session on it.
        player_hash, manager_hash = offline_hashes  # Unpack the precomputed hashes.
        db.add_all([Facility(**row) for row in FACILITIES])  # Insert the demo facilities.
        db.add_all([  # Insert the demo users.
            User(id=DEMO_PLAYER_1_ID, email=DEMO_PLAYER_1_EMAIL, password_hash=player_hash),  # First player.
            User(id=DEMO_PLAYER_2_ID, email=DEMO_PLAYER_2_EMAIL, password_hash=player_hash),  # Second player.
            User(id=DEMO_MANAGER_ID, email=DEMO_MANAGER_EMAIL, password_hash=manager_hash),  # The manager.
        ])  # Finish the users.
        db.flush()  # Send facilities and users first, so foreign keys resolve.
        db.add_all([Field(**row) for row in FIELDS])  # Insert the demo fields.
        db.add(ManagerFacility(user_id=DEMO_MANAGER_ID, facility_id=DEMO_FACILITY_ID))  # Make the manager a manager.
        db.commit()  # Save everything.
        yield db  # Run the test with this session.
    engine.dispose()  # Throw the database away.


@pytest.fixture  # New client for each test.
def isolated_client(isolated_db):  # A client wired to the SQLite database.
    previous = dict(app.dependency_overrides)  # Remember existing overrides.

    def database_override():  # Replacement for get_db.
        yield isolated_db  # Every request uses the test session.

    app.dependency_overrides.clear()  # Start without other overrides.
    app.dependency_overrides[get_db] = database_override  # Route database access to SQLite.
    try:  # Always restore the overrides.
        with TestClient(app) as client:  # Start the app lifecycle.
            yield client  # Run the test.
    finally:  # Runs even if the test fails.
        app.dependency_overrides.clear()  # Remove our override.
        app.dependency_overrides.update(previous)  # Put the old ones back.
