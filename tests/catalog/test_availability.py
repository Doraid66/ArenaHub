"""GET /fields/{field_id}/availability

The conflict rules belong to Person 1's reservation engine. These tests check
Person 3's part: login, input validation, UTC conversion, and that the engine
is asked exactly the right question and its answer is returned.
"""

import importlib.util  # Check whether the engine module exists.
import uuid  # Random IDs.
from datetime import datetime, timezone  # Expected UTC times.

import pytest  # Parametrization and skip markers.

from app.catalog.demo_data import FULL_SOCCER_FIELD_ID, SUB_FIELD_A_ID  # Fields used in tests.

URL = f"/fields/{SUB_FIELD_A_ID}/availability"  # Endpoint under test.
MONTREAL = {"start": "2026-11-15T20:00:00-05:00", "end": "2026-11-15T21:30:00-05:00"}  # A valid interval with an offset.


def test_requires_login(anon_client):  # Logged-out callers are refused.
    r = anon_client.get(URL, params=MONTREAL)  # Call without a token.
    assert r.status_code == 401  # Refused.
    assert r.json()["error"]["code"] == "unauthenticated"  # Shared error code.


@pytest.mark.parametrize("answer", [True, False])  # Both possible answers.
def test_returns_the_engines_answer(client, fake_availability, answer):  # The endpoint relays the engine's answer.
    fake_availability.answer = answer  # Set what the fake engine says.
    r = client.get(URL, params=MONTREAL)  # Ask.
    assert r.status_code == 200  # Success.
    assert r.json()["available"] is answer  # Same answer comes back.


def test_converts_times_to_utc_before_asking_the_engine(client, fake_availability):  # The engine only sees UTC.
    r = client.get(URL, params=MONTREAL)  # Ask with -05:00 times.
    body = r.json()  # Parse the answer.
    assert body["field_id"] == str(SUB_FIELD_A_ID)  # Echoes the field.
    assert body["start"] == "2026-11-16T01:00:00Z"  # 20:00-05:00 is 01:00 UTC next day.
    assert body["end"] == "2026-11-16T02:30:00Z"  # 21:30-05:00 is 02:30 UTC next day.
    assert fake_availability.calls == [(  # The engine was asked exactly once...
        SUB_FIELD_A_ID,  # ...about this field...
        datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc),  # ...with the UTC start...
        datetime(2026, 11, 16, 2, 30, tzinfo=timezone.utc),  # ...and the UTC end.
    )]  # Finish the expected calls.


def test_adjacent_intervals_are_passed_through_unchanged(client, fake_availability):  # No trimming or padding.
    # 08:00-09:00 and 09:00-10:00 may coexist: the endpoint must not trim or pad them.
    client.get(URL, params={"start": "2026-11-15T09:00:00Z", "end": "2026-11-15T10:00:00Z"})  # Ask about 09:00-10:00.
    _, start, end = fake_availability.calls[0]  # What the engine received.
    assert (start.hour, end.hour) == (9, 10)  # Passed through exactly.


def test_parent_field_is_asked_about_itself(client, fake_availability):  # The endpoint does not expand parent/child.
    # Parent/child conflicts are resolved inside the engine; we pass the requested field as-is.
    client.get(f"/fields/{FULL_SOCCER_FIELD_ID}/availability", params=MONTREAL)  # Ask about the parent field.
    assert fake_availability.calls[0][0] == FULL_SOCCER_FIELD_ID  # The engine got the parent ID unchanged.


def error_text(error: dict) -> str:  # Flatten an error into searchable text.
    """The message plus any per-field reasons, as one string."""
    return " ".join([error["message"], *(d["reason"] for d in error.get("details") or [])])  # Message first, then reasons.


@pytest.mark.parametrize(  # Invalid inputs.
    "params, reason",  # Query parameters and a word the error must contain.
    [  # The cases.
        ({"start": "2026-11-15T20:00:00", "end": "2026-11-15T21:00:00-05:00"}, "offset"),  # Start has no offset.
        ({"start": "2026-11-15T20:00:00-05:00", "end": "2026-11-15T21:00:00"}, "offset"),  # End has no offset.
        ({"start": "2026-11-15", "end": "2026-11-16"}, "offset"),  # Bare dates.
        ({"start": "0", "end": "3600"}, "offset"),                    # Not read as Unix time.
        ({"start": "1700000000", "end": "1700003600"}, "offset"),  # Unix-style numbers.
        ({"start": "2026-11-15T21:00:00Z", "end": "2026-11-15T20:00:00Z"}, "after"),  # End before start.
        ({"start": "2026-11-15T20:00:00Z", "end": "2026-11-15T20:00:00Z"}, "after"),  # Empty interval.
        ({"start": "2026-11-15T20:00:00Z"}, "required"),  # End is missing.
        ({"start": "not-a-date", "end": "2026-11-15T20:00:00Z"}, "offset"),  # Not a date at all.
    ],  # Finish the cases.
)  # Finish the parametrization.
def test_rejects_invalid_times(client, fake_availability, params, reason):  # Bad times never reach the engine.
    r = client.get(URL, params=params)  # Ask with bad input.
    assert r.status_code == 422  # Rejected.
    error = r.json()["error"]  # The error envelope.
    assert error["code"] == "invalid_input"  # Shared error code.
    assert reason in error_text(error)  # The message explains the problem.
    assert fake_availability.calls == []  # The engine is never asked.


def test_unknown_field_is_404(client, fake_availability):  # Unknown fields are not found.
    r = client.get(f"/fields/{uuid.uuid4()}/availability", params=MONTREAL)  # Random field ID.
    assert r.status_code == 404  # Not found.
    assert r.json()["error"]["code"] == "not_found"  # Shared error code.
    assert fake_availability.calls == []  # The engine is never asked.


def test_malformed_field_id_is_422(client):  # A non-UUID path is invalid input.
    r = client.get("/fields/not-a-uuid/availability", params=MONTREAL)  # Bad ID.
    assert r.status_code == 422  # Rejected.
    assert r.json()["error"]["code"] == "invalid_input"  # Shared error code.


@pytest.mark.skipif(  # Only relevant before the engine exists.
    importlib.util.find_spec("app.reservations") is not None,  # The engine module exists.
    reason="the real reservation engine is merged",  # Shown in the test report.
)  # Finish the skip marker.
def test_503_until_the_reservation_engine_is_merged(anon_client):  # Missing engine gives 503.
    from app.core.principal import Principal, get_current_principal  # Imported late; only used here.
    from app.main import app  # Imported late; only used here.

    app.dependency_overrides[get_current_principal] = lambda: Principal(user_id=uuid.uuid4())  # Fake login.
    try:  # Always remove the fake login.
        r = anon_client.get(URL, params=MONTREAL)  # Ask.
    finally:  # Runs even if the call fails.
        app.dependency_overrides.clear()  # Remove the fake login.
    assert r.status_code == 503  # Service unavailable.
    assert r.json()["error"]["code"] == "service_unavailable"  # Shared error code.


def test_out_of_range_time_is_422_not_500(client, fake_availability):  # Extreme dates give 422, not a crash.
    # Found by Schemathesis: converting this to UTC lands before year 1.
    r = client.get(URL, params={"start": "0001-01-01T00:00:01+00:03", "end": "0001-04-01T00:00:00+12:01"})  # Out-of-range times.
    assert r.status_code == 422  # Rejected cleanly.
    assert "out of range" in error_text(r.json()["error"])  # The message explains why.
    assert fake_availability.calls == []  # The engine is never asked.
