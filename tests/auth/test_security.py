"""Real token and password checks, plus HTTP tests runnable without PostgreSQL."""

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import jsonschema_rs
import pytest
from sqlalchemy import delete

from app.auth.demo_accounts import (
    DEMO_MANAGER_EMAIL, DEMO_MANAGER_ID, DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_1_ID,
    DEMO_PLAYER_2_EMAIL, DEMO_PLAYER_2_ID,
)
from app.auth.models import User
from app.auth.schemas import LoginRequest
from app.auth.security import create_access_token, decode_access_token, hash_password, verify_password
from app.auth.seed import seed_accounts
from app.core.config import get_settings
from app.core.errors import UnauthenticatedError
from tests.auth.offline_fixtures import TEST_MANAGER_PASSWORD, TEST_PLAYER_PASSWORD


def encoded_token(**changes):
    claims = {"sub": str(DEMO_PLAYER_1_ID), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
    claims.update(changes)
    return jwt.encode(claims, get_settings().jwt_secret, algorithm=get_settings().jwt_algorithm)


def test_password_hashes_are_salted_and_verifiable():
    first = hash_password(TEST_PLAYER_PASSWORD)
    second = hash_password(TEST_PLAYER_PASSWORD)
    assert first.startswith("$argon2id$")
    assert first != second
    assert verify_password(first, TEST_PLAYER_PASSWORD)
    assert not verify_password(first, "incorrect")
    assert not verify_password("invalid-hash", TEST_PLAYER_PASSWORD)
    assert not verify_password(first, "\ud800")


def test_issued_token_has_expected_identity_and_lifetime():
    token = create_access_token(DEMO_PLAYER_1_ID)
    claims = jwt.decode(token, get_settings().jwt_secret, algorithms=[get_settings().jwt_algorithm])
    assert decode_access_token(token) == DEMO_PLAYER_1_ID
    assert claims["exp"] - claims["iat"] == get_settings().access_token_expire_minutes * 60
    assert set(claims) == {"sub", "iat", "exp"}


@pytest.mark.parametrize("claims", [
    {}, {"sub": str(DEMO_PLAYER_1_ID)},
    {"exp": 4102444800}, {"sub": "not-a-uuid", "exp": 4102444800},
    {"sub": 123, "exp": 4102444800}, {"sub": None, "exp": 4102444800},
    {"sub": str(DEMO_PLAYER_1_ID), "exp": 1},
    {"sub": str(DEMO_PLAYER_1_ID), "exp": "not-a-time"},
    {"sub": str(DEMO_PLAYER_1_ID), "exp": float("inf")},
    {"sub": str(DEMO_PLAYER_1_ID), "exp": float("nan")},
])
def test_invalid_claims_have_one_generic_failure(claims):
    token = jwt.encode(claims, get_settings().jwt_secret, algorithm=get_settings().jwt_algorithm)
    with pytest.raises(UnauthenticatedError, match="^Authentication required$"):
        decode_access_token(token)


@pytest.mark.parametrize("token", ["", "broken", "a.b.c", "...", "Bearer nonsense"])
def test_malformed_tokens_are_rejected(token):
    with pytest.raises(UnauthenticatedError):
        decode_access_token(token)


@pytest.mark.parametrize("email,password,user_id,facilities", [
    (DEMO_PLAYER_1_EMAIL, TEST_PLAYER_PASSWORD, DEMO_PLAYER_1_ID, []),
    (DEMO_PLAYER_2_EMAIL, TEST_PLAYER_PASSWORD, DEMO_PLAYER_2_ID, []),
    (DEMO_MANAGER_EMAIL, TEST_MANAGER_PASSWORD, DEMO_MANAGER_ID,
     ["10000000-0000-4000-8000-000000000001"]),
])
def test_login_and_me_use_real_tokens(isolated_client, email, password, user_id, facilities):
    response = isolated_client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    assert set(response.json()) == {"access_token", "token_type", "expires_in"}
    assert response.json()["token_type"] == "bearer"
    assert response.json()["expires_in"] == 1800
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    me = isolated_client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json() == {"id": str(user_id), "email": email, "managed_facility_ids": facilities}
    assert isolated_client.get("/fields", headers=headers).status_code == 200


def test_unknown_email_and_wrong_password_are_indistinguishable(isolated_client):
    wrong = isolated_client.post("/auth/login", json={"email": DEMO_PLAYER_1_EMAIL, "password": "wrong"})
    missing = isolated_client.post("/auth/login", json={"email": "unknown@arenahub.test", "password": "wrong"})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json() == {
        "error": {"code": "unauthenticated", "message": "Authentication required"},
    }
    assert wrong.headers["www-authenticate"] == missing.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer", "Bearer broken", "Bearer a.b.c"])
def test_protected_http_routes_refuse_bad_credentials(isolated_client, authorization):
    headers = {} if authorization is None else {"Authorization": authorization}
    for path in ("/auth/me", "/fields"):
        response = isolated_client.get(path, headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Authentication required"
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("attack", ["tampered", "wrong-secret", "wrong-algorithm", "none", "expired", "unknown-user"])
def test_token_attacks_are_rejected_over_http(isolated_client, attack):
    settings = get_settings()
    claims = {"sub": str(DEMO_PLAYER_1_ID), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
    if attack == "wrong-secret":
        token = jwt.encode(claims, "different-test-signing-key-at-least-32-characters", algorithm=settings.jwt_algorithm)
    elif attack == "wrong-algorithm":
        token = jwt.encode(claims, settings.jwt_secret, algorithm="HS384")
    elif attack == "none":
        token = jwt.encode(claims, "", algorithm="none")
    elif attack == "expired":
        token = encoded_token(exp=1)
    elif attack == "unknown-user":
        token = encoded_token(sub=str(uuid.uuid4()))
    else:
        header, payload, signature = create_access_token(DEMO_PLAYER_1_ID).split(".")
        claims["sub"] = str(DEMO_PLAYER_2_ID)
        payload = base64.urlsafe_b64encode(json.dumps(claims, default=lambda value: int(value.timestamp())).encode()).rstrip(b"=").decode()
        token = f"{header}.{payload}.{signature}"
    response = isolated_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Authentication required"


def test_deleted_account_cannot_keep_using_a_valid_token(isolated_client, isolated_db):
    token = create_access_token(DEMO_PLAYER_2_ID)
    isolated_db.execute(delete(User).where(User.id == DEMO_PLAYER_2_ID))
    isolated_db.commit()
    response = isolated_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.parametrize("extra", [{"user_id": str(DEMO_MANAGER_ID)}, {"role": "manager"}, {"managed_facility_ids": ["x"]}])
def test_login_cannot_grant_identity_or_permissions(isolated_client, extra):
    body = {"email": DEMO_PLAYER_1_EMAIL, "password": TEST_PLAYER_PASSWORD, **extra}
    response = isolated_client.post("/auth/login", json=body)
    assert response.status_code == 422
    assert TEST_PLAYER_PASSWORD not in response.text


@pytest.mark.parametrize("body", [
    {}, {"email": "x\x00@arenahub.test", "password": "test"},
    {"email": DEMO_PLAYER_1_EMAIL, "password": 123},
    {"email": DEMO_PLAYER_1_EMAIL, "password": "x" * 1025},
])
def test_invalid_login_input_is_a_safe_validation_error(isolated_client, body):
    response = isolated_client.post("/auth/login", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"


def test_login_normalizes_email_case(isolated_client):
    response = isolated_client.post("/auth/login", json={
        "email": DEMO_PLAYER_1_EMAIL.upper(), "password": TEST_PLAYER_PASSWORD,
    })
    assert response.status_code == 200


def test_email_whitespace_rejection_matches_the_published_contract(isolated_client):
    # The randomized contract check found that Unicode NEXT LINE was rejected by
    # runtime validation but accepted by the original OpenAPI regex.
    payload = {"email": "r@a\u0085b", "password": "test-only"}
    assert not jsonschema_rs.is_valid(LoginRequest.model_json_schema(), payload)
    response = isolated_client.post("/auth/login", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["email", "password"])
def test_invalid_unicode_input_does_not_crash(isolated_client, field):
    payload = {"email": DEMO_PLAYER_1_EMAIL, "password": TEST_PLAYER_PASSWORD}
    payload[field] = "\ud800@arenahub.test" if field == "email" else "\ud800"
    response = isolated_client.post(
        "/auth/login", content=json.dumps(payload), headers={"Content-Type": "application/json"},
    )
    assert response.status_code in (401, 422)
    assert "traceback" not in response.text.lower()


@pytest.mark.parametrize("missing", ["seed_player_password", "seed_manager_password"])
def test_seed_missing_configuration_is_clear_and_does_not_write(monkeypatch, missing):
    values = {"seed_player_password": TEST_PLAYER_PASSWORD, "seed_manager_password": TEST_MANAGER_PASSWORD}
    values[missing] = None
    monkeypatch.setattr("app.auth.seed.get_settings", lambda: SimpleNamespace(**values))
    db = Mock()
    with pytest.raises(RuntimeError, match=missing.upper()):
        seed_accounts(db)
    db.execute.assert_not_called()
