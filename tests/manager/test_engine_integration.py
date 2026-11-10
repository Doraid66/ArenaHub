"""Real PostgreSQL/reservation integration checks, enabled when Person 1 merges."""

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.demo_accounts import DEMO_MANAGER_EMAIL, DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_1_ID
from app.catalog.demo_data import BASKETBALL_COURT_ID
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import ForbiddenError
from app.core.principal import Principal
from app.main import app

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("app.reservations") is None or "/bookings/{booking_id}" not in app.openapi()["paths"],
    reason="Person 1's reservation engine and booking routes are not integrated yet",
)


def login_headers(client, manager=False):
    settings = get_settings()
    response = client.post("/auth/login", json={
        "email": DEMO_MANAGER_EMAIL if manager else DEMO_PLAYER_1_EMAIL,
        "password": settings.seed_manager_password if manager else settings.seed_player_password,
    })
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def interval(days):
    start = datetime.now(timezone.utc) + timedelta(days=days)
    return {"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}


def test_real_engine_checks_manager_guard_at_write_boundary():
    from app.reservations.service import ReservationService

    payload = interval(45)
    with SessionLocal() as db, pytest.raises(ForbiddenError):
        ReservationService(db).create_block(
            Principal(DEMO_PLAYER_1_ID), BASKETBALL_COURT_ID,
            datetime.fromisoformat(payload["start"]), datetime.fromisoformat(payload["end"]), str(uuid.uuid4()),
        )


def test_real_block_idempotency_and_booking_conflict(anon_client):
    manager = login_headers(anon_client, manager=True)
    player = login_headers(anon_client)
    payload = interval(46)
    path = f"/fields/{BASKETBALL_COURT_ID}/blocks"
    block_headers = {**manager, "Idempotency-Key": str(uuid.uuid4())}
    first = anon_client.post(path, headers=block_headers, json=payload)
    assert first.status_code == 201
    replay = anon_client.post(path, headers=block_headers, json=payload)
    assert replay.status_code == 201
    assert replay.json() == first.json()
    different = {**payload, "end": (datetime.fromisoformat(payload["end"]) + timedelta(minutes=1)).isoformat()}
    reused = anon_client.post(path, headers=block_headers, json=different)
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "idempotency_conflict"
    overlap = anon_client.post(
        f"/fields/{BASKETBALL_COURT_ID}/bookings",
        headers={**player, "Idempotency-Key": str(uuid.uuid4())}, json=payload,
    )
    assert overlap.status_code == 409
    assert overlap.json()["error"]["code"] == "slot_unavailable"


def test_real_manager_cannot_block_an_existing_booking(anon_client):
    player = login_headers(anon_client)
    manager = login_headers(anon_client, manager=True)
    payload = interval(47)
    booking = anon_client.post(
        f"/fields/{BASKETBALL_COURT_ID}/bookings",
        headers={**player, "Idempotency-Key": str(uuid.uuid4())}, json=payload,
    )
    assert booking.status_code == 201
    block = anon_client.post(
        f"/fields/{BASKETBALL_COURT_ID}/blocks",
        headers={**manager, "Idempotency-Key": str(uuid.uuid4())}, json=payload,
    )
    assert block.status_code == 409
    assert block.json()["error"]["code"] == "slot_unavailable"
    assert anon_client.delete(f"/bookings/{booking.json()['id']}", headers=player).status_code == 204


def test_real_engine_rejects_new_blocks_in_the_past(anon_client):
    response = anon_client.post(
        f"/fields/{BASKETBALL_COURT_ID}/blocks",
        headers={**login_headers(anon_client, manager=True), "Idempotency-Key": str(uuid.uuid4())},
        json=interval(-2),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"
