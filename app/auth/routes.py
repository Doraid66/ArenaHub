"""Thin HTTP adapter for login and the current user's public account details."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest, TokenOut, UserOut
from app.auth.service import AuthService
from app.core.database import get_db
from app.core.errors import error_responses
from app.core.principal import Principal, get_current_principal

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post("/login", response_model=TokenOut, responses=error_responses(401))
def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)) -> TokenOut:
    return service.login(body.email, body.password)


@router.get("/me", response_model=UserOut, responses=error_responses(401))
def me(
    principal: Principal = Depends(get_current_principal),
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    return service.me(principal)
