"""HTTP routes for the catalog. Thin: read the request, call the service, return the result."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.catalog.schemas import FieldListOut
from app.catalog.service import CatalogService
from app.core.database import get_db
from app.core.errors import error_responses
from app.core.principal import Principal, get_current_principal

router = APIRouter(tags=["catalog"])


def get_catalog_service(db: Session = Depends(get_db)) -> CatalogService:
    return CatalogService(db)


@router.get(
    "/fields",
    response_model=FieldListOut,
    summary="List all fields",
    responses=error_responses(401),
)
def list_fields(
    principal: Principal = Depends(get_current_principal),  # login required
    service: CatalogService = Depends(get_catalog_service),
) -> FieldListOut:
    return service.list_fields()