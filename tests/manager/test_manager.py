"""Authorization and delegation with real memberships and a test-only block writer."""

import importlib.util
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import jwt
import pytest
from fastapi import Depends
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth.demo_accounts import DEMO_MANAGER_ID, DEMO_PLAYER_1_ID
from app.auth.models import ManagerFacility
from app.auth.security import create_access_token
from app.catalog.demo_data import BASKETBALL_COURT_ID, DEMO_FACILITY_ID, OTHER_SOCCER_FIELD_ID
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import ForbiddenError, InvalidInputError, SlotUnavailableError
from app.core.principal import Principal, require_facility_manager
from app.main import app
from app.manager.routes import get_manager_service
from app.manager.schemas import BlockOut
from app.manager.service import ManagerService


@dataclass
class FakeBlockWriter:
    """Only captures delegation; it never implements conflicts, locks, or persistence."""

    calls: list = field(default_factory=list)
    conflict: bool = False

    def create_block(self, principal, field_id, start, end, idempotency_key):
        self.calls.append((principal, field_id, start, end, idempotency_key))
        if self.conflict:
            raise SlotUnavailableError()
        return BlockOut(id=uuid.uuid4(), field_id=field_id, start=start, end=end)


@pytest.fixture
def writer(isolated_client):
    fake = FakeBlockWriter()

    def service(db: Session = Depends(get_db)):
        return ManagerService(db, fake)

    app.dependency_overrides[get_manager_service] = service
    return fake


def headers(user_id=DEMO_MANAGER_ID):
    return {"Authorization": f"Bearer {create_access_token(user_id)}", "Idempotency-Key": "manager-test-1"}


def body():
    offset = timezone(timedelta(hours=-5))
    start = datetime.now(offset) + timedelta(days=2)
    return {"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}


def test_manager_block_delegates_identity_utc_times_and_key(isolated_client, writer):
    payload = body()
    response = isolated_client.post(f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=headers(), json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "ACTIVE"
    assert set(response.json()) == {"id", "field_id", "status", "start", "end"}
    principal, field_id, start, end, key = writer.calls[0]
    assert principal == Principal(DEMO_MANAGER_ID)
    assert field_id == BASKETBALL_COURT_ID
    assert start.utcoffset() == end.utcoffset() == timedelta(0)
    assert start == datetime.fromisoformat(payload["start"])
    assert key == "manager-test-1"


@pytest.mark.parametrize("user_id,field_id", [
    (DEMO_PLAYER_1_ID, BASKETBALL_COURT_ID), (DEMO_MANAGER_ID, OTHER_SOCCER_FIELD_ID),
])
def test_non_manager_and_other_facility_are_forbidden(isolated_client, writer, user_id, field_id):
    response = isolated_client.post(f"/fields/{field_id}/blocks", headers=headers(user_id), json=body())
    assert response.status_code == 403
    assert writer.calls == []


def test_service_itself_checks_manager_rights(isolated_db):
    fake = FakeBlockWriter()
    payload = body()
    with pytest.raises(ForbiddenError):
        ManagerService(isolated_db, fake).create_block(
            Principal(DEMO_PLAYER_1_ID), BASKETBALL_COURT_ID,
            datetime.fromisoformat(payload["start"]), datetime.fromisoformat(payload["end"]), "key",
        )
    assert fake.calls == []


def test_guard_is_available_to_reservation_engine(isolated_db):
    require_facility_manager(Principal(DEMO_MANAGER_ID), DEMO_FACILITY_ID, isolated_db)
    with pytest.raises(ForbiddenError):
        require_facility_manager(Principal(DEMO_PLAYER_1_ID), DEMO_FACILITY_ID, isolated_db)


def test_unknown_field_is_not_found(isolated_client, writer):
    response = isolated_client.post(f"/fields/{uuid.uuid4()}/blocks", headers=headers(), json=body())
    assert response.status_code == 404
    assert writer.calls == []


def test_token_role_claims_cannot_grant_manager_access(isolated_client, writer):
    settings = get_settings()
    token = jwt.encode({
        "sub": str(DEMO_PLAYER_1_ID), "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        "role": "manager", "managed_facility_ids": [str(DEMO_FACILITY_ID)],
    }, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    response = isolated_client.post(
        f"/fields/{BASKETBALL_COURT_ID}/blocks", json=body(),
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "forged-role"},
    )
    assert response.status_code == 403
    assert writer.calls == []


def test_revoking_database_membership_takes_effect_with_existing_token(isolated_client, isolated_db, writer):
    authorization = headers()
    isolated_db.execute(delete(ManagerFacility).where(ManagerFacility.user_id == DEMO_MANAGER_ID))
    isolated_db.commit()
    response = isolated_client.post(f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=authorization, json=body())
    assert response.status_code == 403
    assert writer.calls == []


@pytest.mark.parametrize("extra", [{"user_id": str(DEMO_MANAGER_ID)}, {"role": "manager"}, {"facility_id": str(DEMO_FACILITY_ID)}])
def test_block_body_cannot_choose_owner_or_permissions(isolated_client, writer, extra):
    response = isolated_client.post(
        f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=headers(), json={**body(), **extra},
    )
    assert response.status_code == 422
    assert writer.calls == []


@pytest.mark.parametrize("invalid", ["reversed", "equal", "naive", "numeric", "overflow"])
def test_invalid_times_never_reach_engine(isolated_client, writer, invalid):
    payload = body()
    if invalid == "reversed":
        payload["start"], payload["end"] = payload["end"], payload["start"]
    elif invalid == "equal":
        payload["end"] = payload["start"]
    elif invalid == "naive":
        payload["start"] = "2030-01-01T20:00:00"
    elif invalid == "numeric":
        payload["start"] = 1700000000
    else:
        payload["start"] = "0001-01-01T00:00:01+00:03"
    response = isolated_client.post(f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=headers(), json=payload)
    assert response.status_code == 422
    assert writer.calls == []


@pytest.mark.parametrize("key", [None, "", "x" * 201, "contains space"])
def test_idempotency_key_is_required_and_bounded(isolated_client, writer, key):
    authorization = headers()
    if key is None:
        authorization.pop("Idempotency-Key")
    else:
        authorization["Idempotency-Key"] = key
    response = isolated_client.post(f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=authorization, json=body())
    assert response.status_code == 422
    assert writer.calls == []


def test_shared_engine_conflict_uses_the_common_error_envelope(isolated_client, writer):
    writer.conflict = True
    response = isolated_client.post(f"/fields/{BASKETBALL_COURT_ID}/blocks", headers=headers(), json=body())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "slot_unavailable"


def test_anonymous_block_is_unauthenticated(isolated_client, writer):
    response = isolated_client.post(
        f"/fields/{BASKETBALL_COURT_ID}/blocks", headers={"Idempotency-Key": "anonymous"}, json=body(),
    )
    assert response.status_code == 401
    assert writer.calls == []


@pytest.mark.skipif(importlib.util.find_spec("app.reservations") is not None, reason="Reservation engine has merged")
def test_missing_engine_is_503_only_after_authorization(isolated_client):
    path = f"/fields/{BASKETBALL_COURT_ID}/blocks"
    assert isolated_client.post(path, headers=headers(DEMO_PLAYER_1_ID), json=body()).status_code == 403
    response = isolated_client.post(path, headers=headers(), json=body())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"


def test_direct_service_rejects_naive_times(isolated_db):
    fake = FakeBlockWriter()
    with pytest.raises(InvalidInputError):
        ManagerService(isolated_db, fake).create_block(
            Principal(DEMO_MANAGER_ID), BASKETBALL_COURT_ID,
            datetime(2030, 1, 1, 20), datetime(2030, 1, 1, 21), "key",
        )
    assert fake.calls == []


def test_retry_can_reach_engine_after_original_block_start(isolated_db):
    # A completed request must still reach the engine's stored idempotency result
    # when the client retries after the block has begun.
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    end = start + timedelta(hours=2)
    stored = BlockOut(id=uuid.uuid4(), field_id=BASKETBALL_COURT_ID, start=start, end=end)
    writer = Mock()
    writer.create_block.return_value = stored
    result = ManagerService(isolated_db, writer).create_block(
        Principal(DEMO_MANAGER_ID), BASKETBALL_COURT_ID, start, end, "completed-request",
    )
    assert result is stored
    writer.create_block.assert_called_once_with(
        Principal(DEMO_MANAGER_ID), BASKETBALL_COURT_ID, start, end, "completed-request",
    )
