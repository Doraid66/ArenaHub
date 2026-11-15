"""Password hashing and JWT signing/validation. No database access or HTTP responses."""

import secrets  # Make a random password for the dummy hash.
import uuid  # User IDs are UUIDs.
from datetime import datetime, timedelta, timezone  # Build token issue and expiry times.

import jwt  # Sign and verify JSON Web Tokens.
from argon2 import PasswordHasher  # Argon2 password hashing.
from argon2.exceptions import InvalidHashError, VerificationError  # Raised on a wrong password or broken hash.

from app.core.config import get_settings  # Secret, algorithm, and token lifetime.
from app.core.errors import UnauthenticatedError  # The one shared 401 error.

_password_hasher = PasswordHasher()  # Argon2id, with a fresh salt on every hash.
# Unknown emails still perform a real password verification, reducing account enumeration
# through the obvious "no hashing happened" timing difference. This is not a demo account.
DUMMY_PASSWORD_HASH = _password_hasher.hash(secrets.token_urlsafe(32))  # Hash of a random password, so unknown emails cost the same time.


def hash_password(password: str) -> str:  # Turn a password into a storable hash.
    return _password_hasher.hash(password)  # New random salt each call.


def verify_password(password_hash: str, password: str) -> bool:  # Check a password against its hash.
    try:  # The library signals failure with exceptions.
        return _password_hasher.verify(password_hash, password)  # True when the password matches.
    except (VerificationError, InvalidHashError, UnicodeError):  # Wrong password, broken hash, or bad text.
        return False  # Treat every failure as "not valid".


def create_access_token(user_id: uuid.UUID) -> str:  # Issue a signed token for this user.
    settings = get_settings()  # Read the secret and lifetime.
    now = datetime.now(timezone.utc)  # Issue time in UTC.
    return jwt.encode(  # Sign the claims.
        {"sub": str(user_id), "iat": now,  # sub is who the token is for; iat is when it was issued.
         "exp": now + timedelta(minutes=settings.access_token_expire_minutes)},  # exp is when it stops working.
        settings.jwt_secret,  # The signing key.
        algorithm=settings.jwt_algorithm,  # The signing algorithm, e.g. HS256.
    )  # Finish the token.


def decode_access_token(token: str) -> uuid.UUID:  # Check a token and return the user ID.
    """Return only identity, never permissions supplied in token claims."""
    settings = get_settings()  # Read the secret and algorithm.
    try:  # Any failure below becomes the same generic 401.
        claims = jwt.decode(  # Verify the signature and expiry.
            token,  # The bearer token from the request.
            settings.jwt_secret,  # The same key used to sign.
            algorithms=[settings.jwt_algorithm],  # Accept only the expected algorithm.
            options={"require": ["exp", "sub"]},  # Both claims must be present.
        )  # Finish decoding.
        return uuid.UUID(claims["sub"])  # Trust only the user ID from the token.
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError, AttributeError):  # Bad signature, expired, wrong shape, or bad UUID.
        # Every authentication failure has the same public message and status.
        raise UnauthenticatedError() from None  # Same error for every failure; hide the cause.
