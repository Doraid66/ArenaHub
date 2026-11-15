"""Thin HTTP adapter for authorized manager blocks."""

import uuid  # Path IDs are UUIDs.
from typing import Annotated  # Attach header details to a type.

from fastapi import APIRouter, Depends, Header  # Router, dependency injection, and headers.
from sqlalchemy.orm import Session  # The request's database session.

from app.core.database import get_db  # Gives each request its own session.
from app.core.errors import error_responses  # Documents error responses in OpenAPI.
from app.core.principal import Principal, get_current_principal  # The verified caller.
from app.manager.schemas import BlockOut, BlockRequest  # Request and response shapes.
from app.manager.service import ManagerService  # Holds the block rules.

router = APIRouter(tags=["manager"])  # Group these routes under "manager" in the docs.


def get_manager_service(db: Session = Depends(get_db)) -> ManagerService:  # Build the service for one request.
    return ManagerService(db)  # Share the request's session.


@router.post(  # POST /fields/{field_id}/blocks.
    "/fields/{field_id}/blocks",  # URL path with the field ID.
    status_code=201,  # A new block was created.
    response_model=BlockOut,  # Shape of the JSON answer.
    responses=error_responses(403, 404, 409, 422, 503),  # Documents the possible errors.
)  # Finish the route declaration.
def create_block(  # Block a field for an interval.
    field_id: uuid.UUID,  # The field from the URL.
    body: BlockRequest,  # Start and end of the block.
    idempotency_key: Annotated[str, Header(  # Retry key from the request header.
        alias="Idempotency-Key", min_length=1, max_length=200, pattern=r"^[\x21-\x7e]+$",  # 1-200 visible ASCII characters.
    )],  # Finish the header declaration.
    principal: Principal = Depends(get_current_principal),  # Identity comes from the verified token.
    service: ManagerService = Depends(get_manager_service),  # Service built for this request.
) -> BlockOut:  # Return the created block.
    return service.create_block(principal, field_id, body.start, body.end, idempotency_key)  # The service authorizes and delegates.
