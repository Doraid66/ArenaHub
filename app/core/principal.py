"""Who is calling? The shared login interface used by every protected route.

OWNER: Person 2. Shared identity and manager guards used by every protected service.
"""

import uuid  # User IDs are UUIDs.
from dataclasses import dataclass  # Simple immutable data class.

from fastapi import Depends, Security  # Dependency injection and security schemes.
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # Read "Authorization: Bearer ...".
from sqlalchemy.orm import Session  # The request's database session.

from app.auth import repository  # Account queries.
from app.auth.security import decode_access_token  # Verify a token.
from app.core.database import get_db  # Gives each request its own session.
from app.core.errors import ForbiddenError, UnauthenticatedError  # Shared 403 and 401 errors.

# Tells FastAPI (and /docs) that protected routes expect "Authorization: Bearer <token>".
# auto_error=False: we raise our own 401 in the shared error format instead of FastAPI's.
bearer_scheme = HTTPBearer(auto_error=False)  # Missing headers reach our code instead of FastAPI's error.


@dataclass(frozen=True)  # Immutable, so identity cannot change mid-request.
class Principal:  # The caller of a request.
    """The authenticated caller. Identity always comes from the verified token."""

    user_id: uuid.UUID  # The only fact we trust from the token.


def get_current_principal(  # Dependency that identifies the caller.
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),  # The bearer token, if sent.
    db: Session = Depends(get_db),  # The request's session.
) -> Principal:  # The verified caller.
    """Verify a bearer token and confirm its subject still exists in the database."""
    if credentials is None or credentials.scheme.lower() != "bearer":  # No token, or the wrong kind.
        raise UnauthenticatedError()  # Return a 401.
    user_id = decode_access_token(credentials.credentials)  # Verify the token; raises 401 if bad.
    if repository.get_user(db, user_id) is None:  # The account was deleted after the token was issued.
        raise UnauthenticatedError()  # Return a 401.
    return Principal(user_id=user_id)  # The caller is verified.


def require_facility_manager(principal: Principal, facility_id: uuid.UUID, db: Session) -> None:  # Guard for manager-only actions.
    """Raise 403 unless the database grants the caller membership of this facility."""
    if not repository.has_manager_membership(db, principal.user_id, facility_id):  # Not a manager of this facility.
        raise ForbiddenError()  # Return a 403.
