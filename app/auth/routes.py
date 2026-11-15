"""Thin HTTP adapter for login and the current user's public account details."""

from fastapi import APIRouter, Depends  # Router plus dependency injection.
from sqlalchemy.orm import Session  # The request's database session.

from app.auth.schemas import LoginRequest, TokenOut, UserOut  # Request and response shapes.
from app.auth.service import AuthService  # Holds the login rules.
from app.core.database import get_db  # Gives each request its own session.
from app.core.errors import error_responses  # Documents error responses in OpenAPI.
from app.core.principal import Principal, get_current_principal  # The verified caller.

router = APIRouter(prefix="/auth", tags=["auth"])  # All routes here start with /auth.


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:  # Build the service for one request.
    return AuthService(db)  # Share the request's session.


@router.post("/login", response_model=TokenOut, responses=error_responses(401))  # POST /auth/login; may answer 401.
def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)) -> TokenOut:  # Exchange credentials for a token.
    return service.login(body.email, body.password)  # The service checks the password.


@router.get("/me", response_model=UserOut, responses=error_responses(401))  # GET /auth/me; may answer 401.
def me(  # Describe the logged-in user.
    principal: Principal = Depends(get_current_principal),  # Identity comes from the verified token.
    service: AuthService = Depends(get_auth_service),  # Service built for this request.
) -> UserOut:  # Public account details only.
    return service.me(principal)  # Look up the caller's account.
