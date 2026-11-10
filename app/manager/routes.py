"""Thin HTTP adapter for authorized manager blocks."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import error_responses
from app.core.principal import Principal, get_current_principal
from app.manager.schemas import BlockOut, BlockRequest
from app.manager.service import ManagerService

router = APIRouter(tags=["manager"])


def get_manager_service(db: Session = Depends(get_db)) -> ManagerService:
    return ManagerService(db)


@router.post(
    "/fields/{field_id}/blocks",
    status_code=201,
    response_model=BlockOut,
    responses=error_responses(403, 404, 409, 422, 503),
)
def create_block(
    field_id: uuid.UUID,
    body: BlockRequest,
    idempotency_key: Annotated[str, Header(
        alias="Idempotency-Key", min_length=1, max_length=200, pattern=r"^[\x21-\x7e]+$",
    )],
    principal: Principal = Depends(get_current_principal),
    service: ManagerService = Depends(get_manager_service),
) -> BlockOut:
    return service.create_block(principal, field_id, body.start, body.end, idempotency_key)
