"""Real booking-security integration; collected automatically after Person 1 merges."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.demo_accounts import DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_2_EMAIL, DEMO_PLAYER_2_ID
from app.catalog.demo_data import BASKETBALL_COURT_ID
from app.core.config import get_settings
from app.main import app

pytestmark = pytest.mark.skipif(
    "/bookings/{booking_id}" not in app.openapi()["paths"],
    reason="Person 1's booking routes are not registered yet",
)


def login_headers(client, email):
    response = client.post("/auth/login", json={
        "email": email, "password": get_settings().seed_player_password,
    })
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_another_player_cannot_read_or_cancel_a_booking(anon_client):
    owner = login_headers(anon_client, DEMO_PLAYER_1_EMAIL)
    other = login_headers(anon_client, DEMO_PLAYER_2_EMAIL)
    start = datetime.now(timezone.utc) + timedelta(days=30)
    response = anon_client.post(
        f"/fields/{BASKETBALL_COURT_ID}/bookings",
        headers={**owner, "Idempotency-Key": str(uuid.uuid4())},
        json={"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()},
    )
    assert response.status_code == 201
    path = f"/bookings/{response.json()['id']}"
    assert anon_client.get(path, headers=other).status_code == 404
    assert anon_client.delete(path, headers=other).status_code == 404
    own_booking = anon_client.get(path, headers=owner)
    assert own_booking.status_code == 200
    assert own_booking.json()["status"] == "HELD"
    assert anon_client.delete(path, headers=owner).status_code == 204


def test_request_cannot_choose_another_booking_owner(anon_client):
    owner = login_headers(anon_client, DEMO_PLAYER_1_EMAIL)
    other = login_headers(anon_client, DEMO_PLAYER_2_EMAIL)
    start = datetime.now(timezone.utc) + timedelta(days=31)
    response = anon_client.post(
        f"/fields/{BASKETBALL_COURT_ID}/bookings",
        headers={**owner, "Idempotency-Key": str(uuid.uuid4())},
        json={"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(),
              "user_id": str(DEMO_PLAYER_2_ID)},
    )
    # Rejecting extra input or ignoring it are safe; using it as authority is not.
    assert response.status_code in (201, 422)
    if response.status_code == 201:
        path = f"/bookings/{response.json()['id']}"
        assert anon_client.get(path, headers=owner).status_code == 200
        assert anon_client.get(path, headers=other).status_code == 404
        assert anon_client.delete(path, headers=owner).status_code == 204
