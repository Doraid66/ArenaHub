"""Who is calling? The shared login interface used by every protected route.

OWNER: Person 2. This file is a PLACEHOLDER added by Person 3 so other modules can be
built and tested against the agreed interface. It rejects every request ("fails closed")
until Person 2 replaces the bodies below with real JWT checks. Keep the names and
signatures exactly as they are.
"""

import uuid
from dataclasses import dataclass

from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

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
) -> Principal:
    """FastAPI dependency: return the caller, or raise 401.

    PLACEHOLDER (Person 2): verify the JWT (signature, algorithm, expiry, subject)
    and return Principal(user_id=...). Until then, every request is rejected.
    """
    if credentials is None:
        raise UnauthenticatedError()
    raise UnauthenticatedError("Login is not implemented yet")


def require_facility_manager(principal: Principal, facility_id: uuid.UUID, db: Session) -> None:
    """Raise 403 unless the caller manages this facility (checked in manager_facilities).

    PLACEHOLDER (Person 2): look up the membership in the database.
    """
    raise ForbiddenError()