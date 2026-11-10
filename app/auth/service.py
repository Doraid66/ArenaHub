"""Login and current-account business rules."""

from sqlalchemy.orm import Session

from app.auth import repository
from app.auth.schemas import TokenOut, UserOut
from app.auth.security import DUMMY_PASSWORD_HASH, create_access_token, verify_password
from app.core.config import get_settings
from app.core.errors import UnauthenticatedError
from app.core.principal import Principal


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def login(self, email: str, password: str) -> TokenOut:
        user = repository.get_user_by_email(self.db, email.strip().lower())
        password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
        valid = verify_password(password_hash, password)
        if user is None or not valid:
            raise UnauthenticatedError()
        return TokenOut(
            access_token=create_access_token(user.id),
            expires_in=get_settings().access_token_expire_minutes * 60,
        )

    def me(self, principal: Principal) -> UserOut:
        user = repository.get_user(self.db, principal.user_id)
        if user is None:
            raise UnauthenticatedError()
        return UserOut(
            id=user.id,
            email=user.email,
            managed_facility_ids=repository.managed_facility_ids(self.db, user.id),
        )
