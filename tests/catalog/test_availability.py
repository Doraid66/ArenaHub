"""GET /fields/{field_id}/availability

The conflict rules belong to Person 1's reservation engine. These tests check
Person 3's part: login, input validation, UTC conversion, and that the engine
is asked exactly the right question and its answer is returned.
"""

import importlib.util
import uuid
from datetime import datetime, timezone

import pytest

from app.catalog.demo_data import FULL_SOCCER_FIELD_ID, SUB_FIELD_A_ID

URL = f"/fields/{SUB_FIELD_A_ID}/availability"
MONTREAL = {"start": "2026-11-15T20:00:00-05:00", "end": "2026-11-15T21:30:00-05:00"}


def test_requires_login(anon_client):
    r = anon_client.get(URL, params=MONTREAL)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize("answer", [True, False])
def test_returns_the_engines_answer(client, fake_availability, answer):
    fake_availability.answer = answer
    r = client.get(URL, params=MONTREAL)
    assert r.status_code == 200
    assert r.json()["available"] is answer


def test_converts_times_to_utc_before_asking_the_engine(client, fake_availability):
    r = client.get(URL, params=MONTREAL)
    body = r.json()
    assert body["field_id"] == str(SUB_FIELD_A_ID)
    assert body["start"] == "2026-11-16T01:00:00Z"
    assert body["end"] == "2026-11-16T02:30:00Z"
    assert fake_availability.calls == [(
        SUB_FIELD_A_ID,
        datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 16, 2, 30, tzinfo=timezone.utc),
    )]


def test_adjacent_intervals_are_passed_through_unchanged(client, fake_availability):
    # 08:00-09:00 and 09:00-10:00 may coexist: the endpoint must not trim or pad them.
    client.get(URL, params={"start": "2026-11-15T09:00:00Z", "end": "2026-11-15T10:00:00Z"})
    _, start, end = fake_availability.calls[0]
    assert (start.hour, end.hour) == (9, 10)


def test_parent_field_is_asked_about_itself(client, fake_availability):
    # Parent/child conflicts are resolved inside the engine; we pass the requested field as-is.
    client.get(f"/fields/{FULL_SOCCER_FIELD_ID}/availability", params=MONTREAL)
    assert fake_availability.calls[0][0] == FULL_SOCCER_FIELD_ID


@pytest.mark.parametrize(
    "params, reason",
    [
        ({"start": "2026-11-15T20:00:00", "end": "2026-11-15T21:00:00-05:00"}, "offset"),
        ({"start": "2026-11-15T20:00:00-05:00", "end": "2026-11-15T21:00:00"}, "offset"),
        ({"start": "2026-11-15T21:00:00Z", "end": "2026-11-15T20:00:00Z"}, "after"),
        ({"start": "2026-11-15T20:00:00Z", "end": "2026-11-15T20:00:00Z"}, "after"),
        ({"start": "2026-11-15T20:00:00Z"}, None),
        ({"start": "not-a-date", "end": "2026-11-15T20:00:00Z"}, None),
    ],
)
def test_rejects_invalid_times(client, fake_availability, params, reason):
    r = client.get(URL, params=params)
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "invalid_input"
    if reason:
        assert reason in error["message"]
    assert fake_availability.calls == []  # the engine is never asked


def test_unknown_field_is_404(client, fake_availability):
    r = client.get(f"/fields/{uuid.uuid4()}/availability", params=MONTREAL)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert fake_availability.calls == []


def test_malformed_field_id_is_422(client):
    r = client.get("/fields/not-a-uuid/availability", params=MONTREAL)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_input"


@pytest.mark.skipif(
    importlib.util.find_spec("app.reservations") is not None,
    reason="the real reservation engine is merged",
)
def test_503_until_the_reservation_engine_is_merged(anon_client):
    from app.core.principal import Principal, get_current_principal
    from app.main import app

    app.dependency_overrides[get_current_principal] = lambda: Principal(user_id=uuid.uuid4())
    try:
        r = anon_client.get(URL, params=MONTREAL)
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "service_unavailable"