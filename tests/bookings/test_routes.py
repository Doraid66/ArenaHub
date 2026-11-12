"""HTTP behavior through real login, validation, routes, and PostgreSQL persistence."""

import uuid  # Fresh retry keys and unknown resource IDs.
from datetime import timedelta  # Construct changed and invalid intervals.

import pytest  # Parameterize malformed request cases.

from app.catalog.demo_data import BASKETBALL_COURT_ID  # Existing seeded surface.

PATH = f"/fields/{BASKETBALL_COURT_ID}/bookings"  # Preserve the agreed field_id URL.


def payload(window):  # JSON timestamps require explicit timezone offsets.
    return {"start": window[0].isoformat(), "end": window[1].isoformat()}  # Use the future relative test interval.


def test_create_get_retry_cancel_and_real_availability(anon_client, auth_headers, window):  # One end-to-end player workflow.
    headers = {**auth_headers["owner"], "Idempotency-Key": str(uuid.uuid4())}  # Caller identity and stable request key.
    response = anon_client.post(PATH, headers=headers, json=payload(window))  # Create the HELD booking.
    assert response.status_code == 201  # A new resource was created.
    booking = response.json()  # Store the original receipt for retry assertions.
    assert set(booking) == {"id", "field_id", "status", "start", "end", "hold_expires_at"}  # No internal or owner fields leak.
    assert booking["status"] == "HELD"  # Payments are outside this milestone.
    path = f"/bookings/{booking['id']}"  # Resource URL for read and cancellation.
    assert anon_client.get(path, headers=headers).json() == booking  # Owner can read its current state.
    availability = f"/fields/{BASKETBALL_COURT_ID}/availability"  # Existing catalog endpoint delegates to the real engine.
    assert anon_client.get(availability, headers=headers, params=payload(window)).json()["available"] is False  # Hold consumes space.
    competing = anon_client.post(PATH, headers={**auth_headers["other"], "Idempotency-Key": str(uuid.uuid4())}, json=payload(window))  # Another real user tries the same interval.
    assert competing.status_code == 409  # Capacity decision belongs to the engine.
    assert competing.json()["error"]["code"] == "slot_unavailable"  # Stable machine-readable conflict code.
    for method in [anon_client.get, anon_client.delete]:  # Neither action may disclose another user's booking.
        assert method(path, headers=auth_headers["other"]).status_code == 404  # Authorization is enforced below the route too.
    for unused in range(2):  # Repeated cancellation is a successful no-op.
        cancelled = anon_client.delete(path, headers=headers)  # Owner releases the held space.
        assert cancelled.status_code == 204 and cancelled.content == b""  # No JSON body on a 204 response.
    assert anon_client.get(path, headers=headers).json()["status"] == "CANCELLED"  # Current-state endpoint reflects the transition.
    assert anon_client.get(availability, headers=headers, params=payload(window)).json()["available"] is True  # Capacity is available again.
    assert anon_client.post(PATH, headers=headers, json=payload(window)).json() == booking  # Retry still returns the original snapshot.
    changed = payload((window[0], window[1] + timedelta(minutes=1)))  # Reuse key with a changed interval.
    conflict = anon_client.post(PATH, headers=headers, json=changed)  # This must not create a different booking.
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_conflict"  # Distinguish retry misuse from capacity conflicts.


@pytest.mark.parametrize("method,path", [("post", PATH), ("get", f"/bookings/{uuid.uuid4()}"), ("delete", f"/bookings/{uuid.uuid4()}")])  # Every booking route requires login.
def test_booking_routes_require_authentication(anon_client, window, method, path):  # Exercise real bearer-token validation.
    arguments = {"headers": {"Idempotency-Key": str(uuid.uuid4())}}  # Missing token, otherwise valid request.
    if method == "post":  # Only creates have a JSON request body.
        arguments["json"] = payload(window)  # Avoid unrelated body validation failures.
    response = getattr(anon_client, method)(path, **arguments)  # Call the public HTTP interface.
    assert response.status_code == 401  # Unknown identity must be rejected.
    assert response.json()["error"]["code"] == "unauthenticated"  # Use the team's consistent error envelope.


@pytest.mark.parametrize("extra", [{"user_id": str(uuid.uuid4())}, {"status": "CONFIRMED"}, {"hold_expires_at": "2099-01-01T00:00:00Z"}])  # All lifecycle and identity fields are server-owned.
def test_create_rejects_spoofed_fields(anon_client, auth_headers, window, extra):  # Reject rather than silently trusting extra properties.
    response = anon_client.post(PATH, headers={**auth_headers["owner"], "Idempotency-Key": str(uuid.uuid4())}, json={**payload(window), **extra})  # Add one forged field.
    assert response.status_code == 422  # Strict request schema rejects it.
    assert response.json()["error"]["code"] == "invalid_input"  # Central validation handler formats the error.


@pytest.mark.parametrize("change", ["naive", "numeric", "reversed", "equal", "past", "overflow"])  # Cover parser and service rules.
def test_invalid_intervals_return_documented_errors(anon_client, auth_headers, window, change):  # No invalid timestamp should become a 500.
    body = payload(window)  # Begin with a valid request.
    if change == "naive":  # Missing timezone offset.
        body["start"] = window[0].replace(tzinfo=None).isoformat()  # Never silently assume the server's timezone.
    elif change == "numeric":  # Pydantic normally accepts epoch numbers unless constrained.
        body["start"] = 0  # The shared timestamp type must reject it.
    elif change == "overflow":  # UTC conversion would fall before year 1.
        body["start"] = "0001-01-01T00:00:01+00:03"  # Shared regression case from Person 3.
    elif change == "past":  # Valid syntax, invalid new-booking time.
        body["start"] = (window[0] - timedelta(days=10)).isoformat()  # The service owns this time-dependent check.
    else:  # End before or equal to start.
        body["end"] = (window[0] - timedelta(minutes=1) if change == "reversed" else window[0]).isoformat()  # Cross-field validation.
    response = anon_client.post(PATH, headers={**auth_headers["owner"], "Idempotency-Key": str(uuid.uuid4())}, json=body)  # Exercise the assembled API.
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_input"  # Stable validation failure.


@pytest.mark.parametrize("key", [None, "", "has space", "x" * 201])  # Missing or invalid retry header.
def test_create_requires_valid_idempotency_key(anon_client, auth_headers, window, key):  # Match Person 2's manager header contract.
    headers = dict(auth_headers["owner"])  # Start with a valid bearer token.
    if key is not None:  # Omitting the header differs from an empty value.
        headers["Idempotency-Key"] = key  # Let FastAPI apply its declared constraints.
    response = anon_client.post(PATH, headers=headers, json=payload(window))  # Capacity is irrelevant for invalid input.
    assert response.status_code == 422  # Every invalid header uses the documented validation response.


def test_unsupported_method_lists_both_booking_methods(anon_client):  # Regression from the generated conformance suite.
    response = anon_client.options(f"/bookings/{uuid.uuid4()}")  # A known resource path with an unsupported method.
    assert response.status_code == 405  # Reject OPTIONS without calling the booking service.
    assert set(response.headers["Allow"].split(", ")) == {"GET", "DELETE"}  # Describe the entire resource, not just the first route match.
    assert response.json()["error"]["code"] == "method_not_allowed"  # Retain Person 3's shared error format.
