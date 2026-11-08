"""Response shapes for the catalog endpoints (they appear in the OpenAPI contract)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FieldOut(BaseModel):
    # from_attributes=True lets Pydantic read a SQLAlchemy Field object directly.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    facility_id: uuid.UUID
    parent_field_id: uuid.UUID | None
    name: str
    sport: str


class FieldListOut(BaseModel):
    items: list[FieldOut]


class AvailabilityOut(BaseModel):
    field_id: uuid.UUID
    start: datetime  # always UTC
    end: datetime    # always UTC
    available: bool