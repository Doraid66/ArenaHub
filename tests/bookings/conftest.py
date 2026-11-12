"""Booking tests use the shared migrated PostgreSQL test database."""

from datetime import datetime, timedelta, timezone  # Future dates keep tests independent of the calendar.

import pytest  # Fixtures isolate each booking scenario.
from sqlalchemy import delete  # Clear only the reservation feature's test tables.

from app.auth.demo_accounts import DEMO_MANAGER_EMAIL, DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_2_EMAIL  # Real seeded demo accounts.
from app.core.config import get_settings  # Test logins use locally configured seed passwords.
from app.core.database import SessionLocal  # The root fixture points this at the disposable test database.
from app.reservations.models import IdempotencyRecord, Reservation  # Tables introduced by migration 0003.
from app.reservations.service import ReservationService  # Test the public use cases directly.


@pytest.fixture(autouse=True)  # Apply isolation only inside tests/bookings/.
def clean_booking_tables(test_database):  # Depend on the shared fixture so migrations finish first.
    def clear():  # Test database cleanup never touches the development database.
        with SessionLocal() as db:  # No test writers are running during fixture cleanup.
            db.execute(delete(IdempotencyRecord))  # Remove retry receipts.
            db.execute(delete(Reservation))  # Remove booking and block occupancy.
            db.commit()  # Start the next scenario with empty feature tables.
    clear()  # Remove state left by earlier test modules.
    yield  # Run the test, including all joined worker threads.
    clear()  # Leave subsequent tests independent of this scenario.


@pytest.fixture  # A real database session per service test.
def booking_db():  # The service is allowed to commit, just as it does in production.
    with SessionLocal() as db:  # Close or roll back remaining reads on exit.
        yield db  # Callers can inspect committed database state too.


@pytest.fixture  # Keep service tests focused on behavior.
def service(booking_db):  # Use the production repository, not a fake capacity engine.
    return ReservationService(booking_db)  # All writes hit PostgreSQL.


@pytest.fixture  # Relative timestamps avoid stale hard-coded future dates.
def window():  # One-hour default interval for most tests.
    start = datetime.now(timezone.utc) + timedelta(days=7)  # Safely in the future.
    return start, start + timedelta(hours=1)  # Half-open interval.


@pytest.fixture  # HTTP tests exercise the real authentication boundary.
def auth_headers(anon_client):  # No dependency override grants a synthetic login.
    result = {}  # Named users make owner and manager assertions readable.
    for name, email in [("owner", DEMO_PLAYER_1_EMAIL), ("other", DEMO_PLAYER_2_EMAIL), ("manager", DEMO_MANAGER_EMAIL)]:  # Login all existing demo identities.
        settings = get_settings()  # Seed passwords are local environment values.
        password = settings.seed_manager_password if name == "manager" else settings.seed_player_password  # Match the account's seed password.
        response = anon_client.post("/auth/login", json={"email": email, "password": password})  # Real hash verification and JWT issuance.
        assert response.status_code == 200  # Fail at setup if authentication is broken.
        result[name] = {"Authorization": f"Bearer {response.json()['access_token']}"}  # Never print the token.
    return result  # Tests add a unique retry key when creating resources.
