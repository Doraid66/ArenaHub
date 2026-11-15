"""Response shapes for the catalog endpoints (they appear in the OpenAPI contract)."""

import uuid  # IDs are UUIDs.
from datetime import datetime  # Timestamps in responses.

from pydantic import BaseModel, ConfigDict  # Validated response models.


class FieldOut(BaseModel):  # One field in a response.
    # from_attributes=True lets Pydantic read a SQLAlchemy Field object directly.
    model_config = ConfigDict(from_attributes=True)  # Allow building this from a database object.

    id: uuid.UUID  # The field's ID.
    facility_id: uuid.UUID  # The facility it belongs to.
    parent_field_id: uuid.UUID | None  # The full field above it, or None.
    name: str  # Display name.
    sport: str  # Sport played here.


class FieldListOut(BaseModel):  # The GET /fields response.
    items: list[FieldOut]  # All fields.


class AvailabilityOut(BaseModel):  # The availability response.
    field_id: uuid.UUID  # The field that was checked.
    start: datetime  # Start of the checked interval, always UTC.
    end: datetime  # End of the checked interval, always UTC.
    available: bool  # True when the whole interval is free.
