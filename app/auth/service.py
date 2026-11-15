"""Login and current-account business rules."""

from sqlalchemy.orm import Session  # The request's database session.

from app.auth import repository  # Account queries.
from app.auth.schemas import TokenOut, UserOut  # Response shapes.
from app.auth.security import DUMMY_PASSWORD_HASH, create_access_token, verify_password  # Password and token helpers.
from app.core.config import get_settings  # Token lifetime setting.
from app.core.errors import UnauthenticatedError  # The shared 401 error.
from app.core.principal import Principal  # The verified caller.


class AuthService:  # Rules for logging in and viewing your own account.
    def __init__(self, db: Session) -> None:  # One service per request.
        self.db = db  # Keep the session for queries.

    def login(self, email: str, password: str) -> TokenOut:  # Check credentials and issue a token.
        user = repository.get_user_by_email(self.db, email.strip().lower())  # Emails are matched in lowercase.
        password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH  # Unknown email still gets hashed work.
        valid = verify_password(password_hash, password)  # Always verify, so timing does not reveal who exists.
        if user is None or not valid:  # Unknown email or wrong password.
            raise UnauthenticatedError()  # Same error for both cases.
        return TokenOut(  # Build the login response.
            access_token=create_access_token(user.id),  # Signed token for this user.
            expires_in=get_settings().access_token_expire_minutes * 60,  # Lifetime in seconds.
        )  # Finish the response.

    def me(self, principal: Principal) -> UserOut:  # Return the caller's own account details.
        user = repository.get_user(self.db, principal.user_id)  # Load the account.
        if user is None:  # The account vanished after the token was issued.
            raise UnauthenticatedError()  # Treat it as logged out.
        return UserOut(  # Build the public view.
            id=user.id,  # The user's ID.
            email=user.email,  # The login email.
            managed_facility_ids=repository.managed_facility_ids(self.db, user.id),  # Facilities they manage.
        )  # Finish the response.
