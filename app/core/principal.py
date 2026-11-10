"""Who is calling? The shared login interface used by every protected route.

OWNER: Person 2. Shared identity and manager guards used by every protected service.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import repository
from app.auth.security import decode_access_token
from app.core.database import get_db
from app.core.errors import ForbiddenError, UnauthenticatedError

# Tells FastAPI (and /docs) that protected routes expect "Authorization: Bearer <token>".
# auto_error=False: we raise our own 401 in the shared error format instead of FastAPI's.
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. Identity always comes from the verified token."""

    user_id: uuid.UUID


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    db: Session = Depends(get_db),
) -> Principal:
    """Verify a bearer token and confirm its subject still exists in the database."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthenticatedError()
    user_id = decode_access_token(credentials.credentials)
    if repository.get_user(db, user_id) is None:
        raise UnauthenticatedError()
    return Principal(user_id=user_id)


def require_facility_manager(principal: Principal, facility_id: uuid.UUID, db: Session) -> None:
    """Raise 403 unless the database grants the caller membership of this facility."""
    if not repository.has_manager_membership(db, principal.user_id, facility_id):
        raise ForbiddenError()
