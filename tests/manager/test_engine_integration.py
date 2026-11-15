"""Real PostgreSQL/reservation integration checks, enabled when Person 1 merges."""

import importlib.util  # Check whether the engine module exists.
import uuid  # Unique retry keys.
from datetime import datetime, timedelta, timezone  # Build intervals.

import pytest  # Skip markers.

from app.auth.demo_accounts import DEMO_MANAGER_EMAIL, DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_1_ID  # Demo accounts.
from app.catalog.demo_data import BASKETBALL_COURT_ID  # Field being blocked and booked.
from app.core.config import get_settings  # Seed passwords for logging in.
from app.core.database import SessionLocal  # Open a real PostgreSQL session.
from app.core.errors import ForbiddenError  # Expected authorization failure.
from app.core.principal import Principal  # The caller identity type.
from app.main import app  # Check which routes exist.

pytestmark = pytest.mark.skipif(  # Skip this whole file until the engine is integrated.
    importlib.util.find_spec("app.reservations") is None or "/bookings/{booking_id}" not in app.openapi()["paths"],  # Engine or routes missing.
    reason="Person 1's reservation engine and booking routes are not integrated yet",  # Shown in the test report.
)  # Finish the skip marker.


def login_headers(client, manager=False):  # Log in as a player or the manager.
    settings = get_settings()  # Seed passwords.
    response = client.post("/auth/login", json={  # Real login request.
        "email": DEMO_MANAGER_EMAIL if manager else DEMO_PLAYER_1_EMAIL,  # Pick the account.
        "password": settings.seed_manager_password if manager else settings.seed_player_password,  # Matching password.
    })  # Finish the request.
    assert response.status_code == 200  # Login must succeed.
    return {"Authorization": f"Bearer {response.json()['access_token']}"}  # Header to reuse in later calls.


def interval(days):  # A one-hour interval some days from now.
    start = datetime.now(timezone.utc) + timedelta(days=days)  # Start time.
    return {"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}  # JSON-ready payload.


def test_real_engine_checks_manager_guard_at_write_boundary():  # The engine itself enforces the manager rule.
    from app.reservations.service import ReservationService  # Imported late; only used here.

    payload = interval(45)  # A future interval.
    with SessionLocal() as db, pytest.raises(ForbiddenError):  # A non-manager must be refused.
        ReservationService(db).create_block(  # Call the engine directly, bypassing HTTP.
            Principal(DEMO_PLAYER_1_ID), BASKETBALL_COURT_ID,  # A player, not a manager.
            datetime.fromisoformat(payload["start"]), datetime.fromisoformat(payload["end"]), str(uuid.uuid4()),  # Interval and a fresh key.
        )  # Finish the call.


def test_real_block_idempotency_and_booking_conflict(anon_client):  # Blocks replay safely and beat bookings.
    manager = login_headers(anon_client, manager=True)  # Manager's header.
    player = login_headers(anon_client)  # Player's header.
    payload = interval(46)  # A future interval.
    path = f"/fields/{BASKETBALL_COURT_ID}/blocks"  # Block URL.
    block_headers = {**manager, "Idempotency-Key": str(uuid.uuid4())}  # Login plus one retry key.
    first = anon_client.post(path, headers=block_headers, json=payload)  # Create the block.
    assert first.status_code == 201  # Created.
    replay = anon_client.post(path, headers=block_headers, json=payload)  # Retry with the same key and body.
    assert replay.status_code == 201  # Still success.
    assert replay.json() == first.json()  # Identical response; no second block.
    different = {**payload, "end": (datetime.fromisoformat(payload["end"]) + timedelta(minutes=1)).isoformat()}  # Same key, changed end.
    reused = anon_client.post(path, headers=block_headers, json=different)  # Reuse the key for a different request.
    assert reused.status_code == 409  # Refused.
    assert reused.json()["error"]["code"] == "idempotency_conflict"  # For the right reason.
    overlap = anon_client.post(  # A player tries to book the blocked time.
        f"/fields/{BASKETBALL_COURT_ID}/bookings",  # Booking URL.
        headers={**player, "Idempotency-Key": str(uuid.uuid4())}, json=payload,  # Login, fresh key, same interval.
    )  # Finish the request.
    assert overlap.status_code == 409  # Refused.
    assert overlap.json()["error"]["code"] == "slot_unavailable"  # The block occupies the field.


def test_real_manager_cannot_block_an_existing_booking(anon_client):  # Bookings also beat blocks.
    player = login_headers(anon_client)  # Player's header.
    manager = login_headers(anon_client, manager=True)  # Manager's header.
    payload = interval(47)  # A future interval.
    booking = anon_client.post(  # The player books first.
        f"/fields/{BASKETBALL_COURT_ID}/bookings",  # Booking URL.
        headers={**player, "Idempotency-Key": str(uuid.uuid4())}, json=payload,  # Login, fresh key, interval.
    )  # Finish the request.
    assert booking.status_code == 201  # Booked.
    block = anon_client.post(  # The manager tries to block the same time.
        f"/fields/{BASKETBALL_COURT_ID}/blocks",  # Block URL.
        headers={**manager, "Idempotency-Key": str(uuid.uuid4())}, json=payload,  # Login, fresh key, same interval.
    )  # Finish the request.
    assert block.status_code == 409  # Refused.
    assert block.json()["error"]["code"] == "slot_unavailable"  # The booking occupies the field.
    assert anon_client.delete(f"/bookings/{booking.json()['id']}", headers=player).status_code == 204  # Clean up.


def test_real_engine_rejects_new_blocks_in_the_past(anon_client):  # Past blocks are invalid.
    response = anon_client.post(  # Try to create a block in the past.
        f"/fields/{BASKETBALL_COURT_ID}/blocks",  # Block URL.
        headers={**login_headers(anon_client, manager=True), "Idempotency-Key": str(uuid.uuid4())},  # Manager login and a fresh key.
        json=interval(-2),  # Two days ago.
    )  # Finish the request.
    assert response.status_code == 422  # Rejected.
    assert response.json()["error"]["code"] == "invalid_input"  # As invalid input.
