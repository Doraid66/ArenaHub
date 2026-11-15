"""Real token and password checks, plus HTTP tests runnable without PostgreSQL."""

import base64  # Hand-build a forged token payload.
import json  # Encode JSON payloads.
import uuid  # Random IDs for unknown users.
from datetime import datetime, timedelta, timezone  # Token expiry times.
from types import SimpleNamespace  # Fake settings object.
from unittest.mock import Mock  # Fake database session.

import jwt  # Create tokens directly.
import jsonschema_rs  # Validate payloads against the published schema.
import pytest  # Fixtures and parametrization.
from sqlalchemy import delete  # Delete a user in a test.

from app.auth.demo_accounts import (  # Fixed demo IDs and emails.
    DEMO_MANAGER_EMAIL, DEMO_MANAGER_ID, DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_1_ID,  # The manager and first player.
    DEMO_PLAYER_2_EMAIL, DEMO_PLAYER_2_ID,  # The second player.
)  # Finish the demo imports.
from app.auth.models import User  # The users table.
from app.auth.schemas import LoginRequest  # The login request model.
from app.auth.security import create_access_token, decode_access_token, hash_password, verify_password  # Code under test.
from app.auth.seed import seed_accounts  # The seeding function.
from app.core.config import get_settings  # Token settings.
from app.core.errors import UnauthenticatedError  # The expected failure.
from tests.auth.offline_fixtures import TEST_MANAGER_PASSWORD, TEST_PLAYER_PASSWORD  # Passwords used by the SQLite fixtures.


def encoded_token(**changes):  # Build a valid token, then tweak its claims.
    claims = {"sub": str(DEMO_PLAYER_1_ID), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}  # A valid default.
    claims.update(changes)  # Apply the requested changes.
    return jwt.encode(claims, get_settings().jwt_secret, algorithm=get_settings().jwt_algorithm)  # Sign with the real key.


def test_password_hashes_are_salted_and_verifiable():  # Hashing works and is salted.
    first = hash_password(TEST_PLAYER_PASSWORD)  # First hash.
    second = hash_password(TEST_PLAYER_PASSWORD)  # Second hash of the same password.
    assert first.startswith("$argon2id$")  # Uses Argon2id.
    assert first != second  # Random salts make hashes differ.
    assert verify_password(first, TEST_PLAYER_PASSWORD)  # Correct password passes.
    assert not verify_password(first, "incorrect")  # Wrong password fails.
    assert not verify_password("invalid-hash", TEST_PLAYER_PASSWORD)  # A broken hash fails safely.
    assert not verify_password(first, "\ud800")  # A lone surrogate fails safely.


def test_issued_token_has_expected_identity_and_lifetime():  # Tokens carry the right claims.
    token = create_access_token(DEMO_PLAYER_1_ID)  # Issue a token.
    claims = jwt.decode(token, get_settings().jwt_secret, algorithms=[get_settings().jwt_algorithm])  # Read its claims.
    assert decode_access_token(token) == DEMO_PLAYER_1_ID  # Decoding gives back the user ID.
    assert claims["exp"] - claims["iat"] == get_settings().access_token_expire_minutes * 60  # Lifetime matches the setting.
    assert set(claims) == {"sub", "iat", "exp"}  # No extra claims, such as roles.


@pytest.mark.parametrize("claims", [  # Broken claim sets.
    {}, {"sub": str(DEMO_PLAYER_1_ID)},  # Nothing, or no expiry.
    {"exp": 4102444800}, {"sub": "not-a-uuid", "exp": 4102444800},  # No subject, or a bad one.
    {"sub": 123, "exp": 4102444800}, {"sub": None, "exp": 4102444800},  # Wrong subject types.
    {"sub": str(DEMO_PLAYER_1_ID), "exp": 1},  # Already expired.
    {"sub": str(DEMO_PLAYER_1_ID), "exp": "not-a-time"},  # Expiry is not a number.
    {"sub": str(DEMO_PLAYER_1_ID), "exp": float("inf")},  # Infinite expiry.
    {"sub": str(DEMO_PLAYER_1_ID), "exp": float("nan")},  # Not-a-number expiry.
])  # Finish the cases.
def test_invalid_claims_have_one_generic_failure(claims):  # Every bad token fails the same way.
    token = jwt.encode(claims, get_settings().jwt_secret, algorithm=get_settings().jwt_algorithm)  # Properly signed but broken.
    with pytest.raises(UnauthenticatedError, match="^Authentication required$"):  # Same generic message every time.
        decode_access_token(token)  # Must refuse it.


@pytest.mark.parametrize("token", ["", "broken", "a.b.c", "...", "Bearer nonsense"])  # Garbage inputs.
def test_malformed_tokens_are_rejected(token):  # Garbage is refused.
    with pytest.raises(UnauthenticatedError):  # Must raise the shared 401 error.
        decode_access_token(token)  # Must refuse it.


@pytest.mark.parametrize("email,password,user_id,facilities", [  # One case per demo account.
    (DEMO_PLAYER_1_EMAIL, TEST_PLAYER_PASSWORD, DEMO_PLAYER_1_ID, []),  # Player: manages nothing.
    (DEMO_PLAYER_2_EMAIL, TEST_PLAYER_PASSWORD, DEMO_PLAYER_2_ID, []),  # Player: manages nothing.
    (DEMO_MANAGER_EMAIL, TEST_MANAGER_PASSWORD, DEMO_MANAGER_ID,  # Manager.
     ["10000000-0000-4000-8000-000000000001"]),  # Manages the demo facility.
])  # Finish the cases.
def test_login_and_me_use_real_tokens(isolated_client, email, password, user_id, facilities):  # Login, then /me, over HTTP.
    response = isolated_client.post("/auth/login", json={"email": email, "password": password})  # Log in.
    assert response.status_code == 200  # Login succeeds.
    assert set(response.json()) == {"access_token", "token_type", "expires_in"}  # Exactly these fields.
    assert response.json()["token_type"] == "bearer"  # Bearer token.
    assert response.json()["expires_in"] == 1800  # 30 minutes in seconds.
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}  # Use the token from now on.
    me = isolated_client.get("/auth/me", headers=headers)  # Ask who we are.
    assert me.status_code == 200  # The token works.
    assert me.json() == {"id": str(user_id), "email": email, "managed_facility_ids": facilities}  # Correct account details.
    assert isolated_client.get("/fields", headers=headers).status_code == 200  # Other protected routes accept it too.


def test_unknown_email_and_wrong_password_are_indistinguishable(isolated_client):  # No account enumeration.
    wrong = isolated_client.post("/auth/login", json={"email": DEMO_PLAYER_1_EMAIL, "password": "wrong"})  # Real email, wrong password.
    missing = isolated_client.post("/auth/login", json={"email": "unknown@arenahub.test", "password": "wrong"})  # Unknown email.
    assert wrong.status_code == missing.status_code == 401  # Both are 401.
    assert wrong.json() == missing.json() == {  # Identical bodies.
        "error": {"code": "unauthenticated", "message": "Authentication required"},  # The shared 401 error.
    }  # Finish the expected body.
    assert wrong.headers["www-authenticate"] == missing.headers["www-authenticate"] == "Bearer"  # Identical headers too.


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer", "Bearer broken", "Bearer a.b.c"])  # Bad credentials.
def test_protected_http_routes_refuse_bad_credentials(isolated_client, authorization):  # Every protected route says 401.
    headers = {} if authorization is None else {"Authorization": authorization}  # No header, or the bad one.
    for path in ("/auth/me", "/fields"):  # Two protected routes.
        response = isolated_client.get(path, headers=headers)  # Call it.
        assert response.status_code == 401  # Refused.
        assert response.json()["error"]["message"] == "Authentication required"  # Generic message.
        assert response.headers["www-authenticate"] == "Bearer"  # Tells the client to use a bearer token.


@pytest.mark.parametrize("attack", ["tampered", "wrong-secret", "wrong-algorithm", "none", "expired", "unknown-user"])  # Known token attacks.
def test_token_attacks_are_rejected_over_http(isolated_client, attack):  # Forged tokens never work.
    settings = get_settings()  # Real settings.
    claims = {"sub": str(DEMO_PLAYER_1_ID), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}  # Valid claims to start from.
    if attack == "wrong-secret":  # Signed with another key.
        token = jwt.encode(claims, "different-test-signing-key-at-least-32-characters", algorithm=settings.jwt_algorithm)  # Wrong key.
    elif attack == "wrong-algorithm":  # Signed with another algorithm.
        token = jwt.encode(claims, settings.jwt_secret, algorithm="HS384")  # Wrong algorithm.
    elif attack == "none":  # The classic unsigned-token attack.
        token = jwt.encode(claims, "", algorithm="none")  # No signature at all.
    elif attack == "expired":  # Past its expiry time.
        token = encoded_token(exp=1)  # Expired long ago.
    elif attack == "unknown-user":  # Valid signature, but the user does not exist.
        token = encoded_token(sub=str(uuid.uuid4()))  # Random user ID.
    else:  # "tampered": change the payload but keep the old signature.
        header, payload, signature = create_access_token(DEMO_PLAYER_1_ID).split(".")  # Split a real token.
        claims["sub"] = str(DEMO_PLAYER_2_ID)  # Pretend to be another user.
        payload = base64.urlsafe_b64encode(json.dumps(claims, default=lambda value: int(value.timestamp())).encode()).rstrip(b"=").decode()  # Re-encode the payload.
        token = f"{header}.{payload}.{signature}"  # Original signature no longer matches.
    response = isolated_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})  # Try to use it.
    assert response.status_code == 401  # Refused.
    assert response.json()["error"]["message"] == "Authentication required"  # Generic message.


def test_deleted_account_cannot_keep_using_a_valid_token(isolated_client, isolated_db):  # Tokens die with their account.
    token = create_access_token(DEMO_PLAYER_2_ID)  # Valid token for player 2.
    isolated_db.execute(delete(User).where(User.id == DEMO_PLAYER_2_ID))  # Delete the account.
    isolated_db.commit()  # Save the deletion.
    response = isolated_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})  # Try the old token.
    assert response.status_code == 401  # Refused.


@pytest.mark.parametrize("extra", [{"user_id": str(DEMO_MANAGER_ID)}, {"role": "manager"}, {"managed_facility_ids": ["x"]}])  # Forged extras.
def test_login_cannot_grant_identity_or_permissions(isolated_client, extra):  # Extra login fields are refused.
    body = {"email": DEMO_PLAYER_1_EMAIL, "password": TEST_PLAYER_PASSWORD, **extra}  # Valid login plus a forged field.
    response = isolated_client.post("/auth/login", json=body)  # Try to log in.
    assert response.status_code == 422  # Rejected as invalid input.
    assert TEST_PLAYER_PASSWORD not in response.text  # The error never echoes the password.


@pytest.mark.parametrize("body", [  # Invalid login bodies.
    {}, {"email": "x\x00@arenahub.test", "password": "test"},  # Empty, or a NUL character in the email.
    {"email": DEMO_PLAYER_1_EMAIL, "password": 123},  # Password is not a string.
    {"email": DEMO_PLAYER_1_EMAIL, "password": "x" * 1025},  # Password is too long.
])  # Finish the cases.
def test_invalid_login_input_is_a_safe_validation_error(isolated_client, body):  # Bad input gives a clean 422.
    response = isolated_client.post("/auth/login", json=body)  # Try to log in.
    assert response.status_code == 422  # Rejected.
    assert response.json()["error"]["code"] == "invalid_input"  # In the shared error format.


def test_login_normalizes_email_case(isolated_client):  # Emails are case-insensitive.
    response = isolated_client.post("/auth/login", json={  # Log in with an uppercase email.
        "email": DEMO_PLAYER_1_EMAIL.upper(), "password": TEST_PLAYER_PASSWORD,  # Same account, different case.
    })  # Finish the request.
    assert response.status_code == 200  # Still works.


def test_email_whitespace_rejection_matches_the_published_contract(isolated_client):  # Runtime and OpenAPI must agree.
    # The randomized contract check found that Unicode NEXT LINE was rejected by
    # runtime validation but accepted by the original OpenAPI regex.
    payload = {"email": "r@a\u0085b", "password": "test-only"}  # Email containing U+0085.
    assert not jsonschema_rs.is_valid(LoginRequest.model_json_schema(), payload)  # The published schema rejects it.
    response = isolated_client.post("/auth/login", json=payload)  # The running app...
    assert response.status_code == 422  # ...rejects it too.


@pytest.mark.parametrize("field", ["email", "password"])  # Try each field.
def test_invalid_unicode_input_does_not_crash(isolated_client, field):  # Broken Unicode never causes a 500.
    payload = {"email": DEMO_PLAYER_1_EMAIL, "password": TEST_PLAYER_PASSWORD}  # Valid login to start from.
    payload[field] = "\ud800@arenahub.test" if field == "email" else "\ud800"  # Insert a lone surrogate.
    response = isolated_client.post(  # Send the raw JSON.
        "/auth/login", content=json.dumps(payload), headers={"Content-Type": "application/json"},  # Bypass the client's own encoding.
    )  # Finish the request.
    assert response.status_code in (401, 422)  # A clean refusal.
    assert "traceback" not in response.text.lower()  # No internals leaked.


@pytest.mark.parametrize("missing", ["seed_player_password", "seed_manager_password"])  # Each required setting.
def test_seed_missing_configuration_is_clear_and_does_not_write(monkeypatch, missing):  # Missing passwords stop the seed early.
    values = {"seed_player_password": TEST_PLAYER_PASSWORD, "seed_manager_password": TEST_MANAGER_PASSWORD}  # Both set.
    values[missing] = None  # Remove one.
    monkeypatch.setattr("app.auth.seed.get_settings", lambda: SimpleNamespace(**values))  # Use these fake settings.
    db = Mock()  # A fake session that records calls.
    with pytest.raises(RuntimeError, match=missing.upper()):  # The message names the missing setting.
        seed_accounts(db)  # Try to seed.
    db.execute.assert_not_called()  # Nothing was written.
