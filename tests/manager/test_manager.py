"""Authorization and delegation with real memberships and a test-only block writer."""

import importlib.util  # Check whether the engine module exists.
import uuid  # Random IDs.
from dataclasses import dataclass, field  # Build the fake writer.
from datetime import datetime, timedelta, timezone  # Build intervals.
from unittest.mock import Mock  # Fake writer for one test.

import jwt  # Forge a token.
import pytest  # Fixtures and parametrization.
from fastapi import Depends  # Dependency injection in the override.
from sqlalchemy import delete  # Delete a membership in a test.
from sqlalchemy.orm import Session  # A database session.

from app.auth.demo_accounts import DEMO_MANAGER_ID, DEMO_PLAYER_1_ID  # Demo users.
from app.auth.models import ManagerFacility  # The memberships table.
from app.auth.security import create_access_token  # Issue real tokens.
from app.catalog.demo_data import BASKETBALL_COURT_ID, DEMO_FACILITY_ID, OTHER_SOCCER_FIELD_ID  # Demo catalog IDs.
from app.core.config import get_settings  # Token settings.
from app.core.database import get_db  # Session dependency.
from app.core.errors import ForbiddenError, InvalidInputError, SlotUnavailableError  # Expected errors.
from app.core.principal import Principal, require_facility_manager  # Caller identity and the manager guard.
from app.main import app  # The application under test.
from app.manager.routes import get_manager_service  # Dependency replaced in tests.
from app.manager.schemas import BlockOut  # The block response shape.
from app.manager.service import ManagerService  # Service under test.


@dataclass  # Plain class that records calls.
class FakeBlockWriter:  # Stands in for the reservation engine.
    """Only captures delegation; it never implements conflicts, locks, or persistence."""

    calls: list = field(default_factory=list)  # Every call received, in order.
    conflict: bool = False  # When True, pretend the slot is taken.

    def create_block(self, principal, field_id, start, end, idempotency_key):  # Same method as the real engine.
        self.calls.append((principal, field_id, start, end, idempotency_key))  # Remember the call.
        if self.conflict:  # The test wants a conflict.
            raise SlotUnavailableError()  # Pretend the slot is taken.
        return BlockOut(id=uuid.uuid4(), field_id=field_id, start=start, end=end)  # Return a fake block.


@pytest.fixture  # New fake for each test.
def writer(isolated_client):  # Install the fake writer in the app.
    fake = FakeBlockWriter()  # The fake.

    def service(db: Session = Depends(get_db)):  # Replacement service factory.
        return ManagerService(db, fake)  # Real service, fake engine.

    app.dependency_overrides[get_manager_service] = service  # Use it for every request.
    return fake  # Tests inspect its calls.


def headers(user_id=DEMO_MANAGER_ID):  # Build auth and retry-key headers.
    return {"Authorization": f"Bearer {create_access_token(user_id)}", "Idempotency-Key": "manager-test-1"}  # Real token plus a fixed key.


def body():  # Build a valid request body.
    offset = timezone(timedelta(hours=-5))  # A non-UTC offset.
    start = datetime.now(offset) + timedelta(days=2)  # Two days from now.
    return {"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}  # One-hour interval.


def test_manager_block_delegates_identity_utc_times_and_key(isolated_client, writer):  # Happy path.
    payload = body()  # A valid body.
    response = isolated_client.post(f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=headers(), json=payload)  # Create the block.
    assert response.status_code == 201  # Created.
    assert response.json()["status"] == "ACTIVE"  # New blocks are active.
    assert set(response.json()) == {"id", "field_id", "status", "start", "end"}  # Exactly these fields.
    principal, field_id, start, end, key = writer.calls[0]  # What the engine received.
    assert principal == Principal(DEMO_MANAGER_ID)  # The caller's identity.
    assert field_id == BASKETBALL_COURT_ID  # The target field.
    assert start.utcoffset() == end.utcoffset() == timedelta(0)  # Times were converted to UTC.
    assert start == datetime.fromisoformat(payload["start"])  # Same instant as requested.
    assert key == "manager-test-1"  # The retry key was passed along.


@pytest.mark.parametrize("user_id,field_id", [  # Callers who must be refused.
    (DEMO_PLAYER_1_ID, BASKETBALL_COURT_ID), (DEMO_MANAGER_ID, OTHER_SOCCER_FIELD_ID),  # A player, and a manager of another facility.
])  # Finish the cases.
def test_non_manager_and_other_facility_are_forbidden(isolated_client, writer, user_id, field_id):  # 403 for both.
    response = isolated_client.post(f"/fields/{field_id}/blocks", headers=headers(user_id), json=body())  # Try to block.
    assert response.status_code == 403  # Forbidden.
    assert writer.calls == []  # The engine was never called.


def test_service_itself_checks_manager_rights(isolated_db):  # Not only the route checks.
    fake = FakeBlockWriter()  # Fake engine.
    payload = body()  # A valid body.
    with pytest.raises(ForbiddenError):  # A player must be refused.
        ManagerService(isolated_db, fake).create_block(  # Call the service directly.
            Principal(DEMO_PLAYER_1_ID), BASKETBALL_COURT_ID,  # A player, not a manager.
            datetime.fromisoformat(payload["start"]), datetime.fromisoformat(payload["end"]), "key",  # Interval and key.
        )  # Finish the call.
    assert fake.calls == []  # The engine was never called.


def test_guard_is_available_to_reservation_engine(isolated_db):  # The shared guard works on its own.
    require_facility_manager(Principal(DEMO_MANAGER_ID), DEMO_FACILITY_ID, isolated_db)  # The manager passes.
    with pytest.raises(ForbiddenError):  # A player is refused.
        require_facility_manager(Principal(DEMO_PLAYER_1_ID), DEMO_FACILITY_ID, isolated_db)  # Not a manager.


def test_unknown_field_is_not_found(isolated_client, writer):  # Unknown fields give 404.
    response = isolated_client.post(f"/fields/{uuid.uuid4()}/blocks", headers=headers(), json=body())  # Random field ID.
    assert response.status_code == 404  # Not found.
    assert writer.calls == []  # The engine was never called.


def test_token_role_claims_cannot_grant_manager_access(isolated_client, writer):  # Forged claims are ignored.
    settings = get_settings()  # Real settings.
    token = jwt.encode({  # A genuinely signed token with extra claims.
        "sub": str(DEMO_PLAYER_1_ID), "exp": datetime.now(timezone.utc) + timedelta(minutes=5),  # A player, valid for 5 minutes.
        "role": "manager", "managed_facility_ids": [str(DEMO_FACILITY_ID)],  # Self-awarded manager powers.
    }, settings.jwt_secret, algorithm=settings.jwt_algorithm)  # Signed with the real key.
    response = isolated_client.post(  # Try to block with it.
        f"/fields/{BASKETBALL_COURT_ID}/blocks", json=body(),  # Block URL and a valid body.
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "forged-role"},  # The forged token.
    )  # Finish the request.
    assert response.status_code == 403  # The database, not the token, decides.
    assert writer.calls == []  # The engine was never called.


def test_revoking_database_membership_takes_effect_with_existing_token(isolated_client, isolated_db, writer):  # Revocation is immediate.
    authorization = headers()  # A valid manager token.
    isolated_db.execute(delete(ManagerFacility).where(ManagerFacility.user_id == DEMO_MANAGER_ID))  # Remove the membership.
    isolated_db.commit()  # Save the removal.
    response = isolated_client.post(f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=authorization, json=body())  # Use the old token.
    assert response.status_code == 403  # No longer allowed.
    assert writer.calls == []  # The engine was never called.


@pytest.mark.parametrize("extra", [{"user_id": str(DEMO_MANAGER_ID)}, {"role": "manager"}, {"facility_id": str(DEMO_FACILITY_ID)}])  # Forged extras.
def test_block_body_cannot_choose_owner_or_permissions(isolated_client, writer, extra):  # Extra body fields are refused.
    response = isolated_client.post(  # Try to block with a forged field.
        f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=headers(), json={**body(), **extra},  # Valid body plus the extra.
    )  # Finish the request.
    assert response.status_code == 422  # Rejected.
    assert writer.calls == []  # The engine was never called.


@pytest.mark.parametrize("invalid", ["reversed", "equal", "naive", "numeric", "overflow"])  # Bad time shapes.
def test_invalid_times_never_reach_engine(isolated_client, writer, invalid):  # Bad times stop early.
    payload = body()  # Start from a valid body.
    if invalid == "reversed":  # End before start.
        payload["start"], payload["end"] = payload["end"], payload["start"]  # Swap them.
    elif invalid == "equal":  # Empty interval.
        payload["end"] = payload["start"]  # Same instant.
    elif invalid == "naive":  # No offset.
        payload["start"] = "2030-01-01T20:00:00"  # Missing timezone.
    elif invalid == "numeric":  # A Unix-style number.
        payload["start"] = 1700000000  # Not text.
    else:  # "overflow": UTC conversion would fall before year 1.
        payload["start"] = "0001-01-01T00:00:01+00:03"  # Extreme date.
    response = isolated_client.post(f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=headers(), json=payload)  # Try to block.
    assert response.status_code == 422  # Rejected.
    assert writer.calls == []  # The engine was never called.


@pytest.mark.parametrize("key", [None, "", "x" * 201, "contains space"])  # Bad retry keys.
def test_idempotency_key_is_required_and_bounded(isolated_client, writer, key):  # Retry key rules.
    authorization = headers()  # A valid starting set of headers.
    if key is None:  # The header is missing.
        authorization.pop("Idempotency-Key")  # Remove it.
    else:  # The header has a bad value.
        authorization["Idempotency-Key"] = key  # Replace it.
    response = isolated_client.post(f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=authorization, json=body())  # Try to block.
    assert response.status_code == 422  # Rejected.
    assert writer.calls == []  # The engine was never called.


def test_shared_engine_conflict_uses_the_common_error_envelope(isolated_client, writer):  # Engine errors keep the shared format.
    writer.conflict = True  # Make the fake report a conflict.
    response = isolated_client.post(f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=headers(), json=body())  # Try to block.
    assert response.status_code == 409  # Conflict.
    assert response.json()["error"]["code"] == "slot_unavailable"  # Shared error code.


def test_anonymous_block_is_unauthenticated(isolated_client, writer):  # Login is required.
    response = isolated_client.post(  # Try to block without a token.
        f"/fields/{BASKETBALL_COURT_ID}/blocks", headers={"Idempotency-Key": "anonymous"}, json=body(),  # Only a retry key.
    )  # Finish the request.
    assert response.status_code == 401  # Refused.
    assert writer.calls == []  # The engine was never called.


@pytest.mark.skipif(importlib.util.find_spec("app.reservations") is not None, reason="Reservation engine has merged")  # Only before the engine exists.
def test_missing_engine_is_503_only_after_authorization(isolated_client):  # Authorization comes before the 503.
    path = f"/fields/{BASKETBALL_COURT_ID}/blocks"  # Block URL.
    assert isolated_client.post(path, headers=headers(DEMO_PLAYER_1_ID), json=body()).status_code == 403  # A player is refused first.
    response = isolated_client.post(path, headers=headers(), json=body())  # A real manager gets further.
    assert response.status_code == 503  # But the engine is missing.
    assert response.json()["error"]["code"] == "service_unavailable"  # Shared error code.


def test_direct_service_rejects_naive_times(isolated_db):  # The service validates times itself.
    fake = FakeBlockWriter()  # Fake engine.
    with pytest.raises(InvalidInputError):  # Naive times must be refused.
        ManagerService(isolated_db, fake).create_block(  # Call the service directly.
            Principal(DEMO_MANAGER_ID), BASKETBALL_COURT_ID,  # An authorized manager.
            datetime(2030, 1, 1, 20), datetime(2030, 1, 1, 21), "key",  # Times without a timezone.
        )  # Finish the call.
    assert fake.calls == []  # The engine was never called.


def test_retry_can_reach_engine_after_original_block_start(isolated_db):  # Late retries still replay.
    # A completed request must still reach the engine's stored idempotency result
    # when the client retries after the block has begun.
    start = datetime.now(timezone.utc) - timedelta(hours=1)  # A block that already started.
    end = start + timedelta(hours=2)  # And is still running.
    stored = BlockOut(id=uuid.uuid4(), field_id=BASKETBALL_COURT_ID, start=start, end=end)  # The engine's stored answer.
    writer = Mock()  # Fake engine that records its call.
    writer.create_block.return_value = stored  # It returns the stored answer.
    result = ManagerService(isolated_db, writer).create_block(  # Retry the request.
        Principal(DEMO_MANAGER_ID), BASKETBALL_COURT_ID, start, end, "completed-request",  # Same request as before.
    )  # Finish the call.
    assert result is stored  # The stored answer came back.
    writer.create_block.assert_called_once_with(  # The service did not block the retry itself.
        Principal(DEMO_MANAGER_ID), BASKETBALL_COURT_ID, start, end, "completed-request",  # Passed through unchanged.
    )  # Finish the assertion.
