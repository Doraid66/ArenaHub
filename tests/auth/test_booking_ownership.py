"""Real booking-security integration; collected automatically after Person 1 merges."""

import uuid  # Unique retry keys.
from datetime import datetime, timedelta, timezone  # Future booking times.

import pytest  # Skip markers.

from app.auth.demo_accounts import DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_2_EMAIL, DEMO_PLAYER_2_ID  # Demo players.
from app.catalog.demo_data import BASKETBALL_COURT_ID  # Field being booked.
from app.core.config import get_settings  # Seed passwords for logging in.
from app.main import app  # Check which routes exist.

pytestmark = pytest.mark.skipif(  # Skip this whole file when the booking routes are missing.
    "/bookings/{booking_id}" not in app.openapi()["paths"],  # Booking routes not registered.
    reason="Person 1's booking routes are not registered yet",  # Shown in the test report.
)  # Finish the skip marker.


def login_headers(client, email):  # Log in and build the auth header.
    response = client.post("/auth/login", json={  # Real login request.
        "email": email, "password": get_settings().seed_player_password,  # Seeded player credentials.
    })  # Finish the request.
    assert response.status_code == 200  # Login must succeed.
    return {"Authorization": f"Bearer {response.json()['access_token']}"}  # Header to reuse in later calls.


def test_another_player_cannot_read_or_cancel_a_booking(anon_client):  # Ownership is enforced.
    owner = login_headers(anon_client, DEMO_PLAYER_1_EMAIL)  # Player 1's header.
    other = login_headers(anon_client, DEMO_PLAYER_2_EMAIL)  # Player 2's header.
    start = datetime.now(timezone.utc) + timedelta(days=30)  # A start time in the future.
    response = anon_client.post(  # Player 1 creates a booking.
        f"/fields/{BASKETBALL_COURT_ID}/bookings",  # Booking URL.
        headers={**owner, "Idempotency-Key": str(uuid.uuid4())},  # Login plus a fresh retry key.
        json={"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()},  # One-hour interval.
    )  # Finish the request.
    assert response.status_code == 201  # Booking was created.
    path = f"/bookings/{response.json()['id']}"  # URL of the new booking.
    assert anon_client.get(path, headers=other).status_code == 404  # Player 2 cannot read it.
    assert anon_client.delete(path, headers=other).status_code == 404  # Player 2 cannot cancel it.
    own_booking = anon_client.get(path, headers=owner)  # The owner reads it.
    assert own_booking.status_code == 200  # The owner can see it.
    assert own_booking.json()["status"] == "HELD"  # Still a temporary hold.
    assert anon_client.delete(path, headers=owner).status_code == 204  # The owner can cancel it.


def test_request_cannot_choose_another_booking_owner(anon_client):  # The owner always comes from the token.
    owner = login_headers(anon_client, DEMO_PLAYER_1_EMAIL)  # Player 1's header.
    other = login_headers(anon_client, DEMO_PLAYER_2_EMAIL)  # Player 2's header.
    start = datetime.now(timezone.utc) + timedelta(days=31)  # A start time in the future.
    response = anon_client.post(  # Try to sneak in another owner.
        f"/fields/{BASKETBALL_COURT_ID}/bookings",  # Booking URL.
        headers={**owner, "Idempotency-Key": str(uuid.uuid4())},  # Login plus a fresh retry key.
        json={"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(),  # One-hour interval.
              "user_id": str(DEMO_PLAYER_2_ID)},  # Forged owner field.
    )  # Finish the request.
    # Rejecting extra input or ignoring it are safe; using it as authority is not.
    assert response.status_code in (201, 422)  # Either rejecting or ignoring is acceptable.
    if response.status_code == 201:  # The extra field was ignored.
        path = f"/bookings/{response.json()['id']}"  # URL of the new booking.
        assert anon_client.get(path, headers=owner).status_code == 200  # Player 1 owns it.
        assert anon_client.get(path, headers=other).status_code == 404  # Player 2 does not.
        assert anon_client.delete(path, headers=owner).status_code == 204  # Clean up.
