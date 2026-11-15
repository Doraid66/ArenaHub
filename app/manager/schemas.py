"""Time-block request and response shapes agreed with the reservation engine."""

import uuid  # IDs are UUIDs.
from datetime import datetime  # Timestamps in responses.
from typing import Literal  # Restrict a field to one exact value.

from pydantic import BaseModel, ConfigDict  # Validated request and response models.

from app.core.timestamps import UtcTimestamp  # Strict timestamp type with a required offset.


class BlockRequest(BaseModel):  # The body of POST /fields/{id}/blocks.
    model_config = ConfigDict(extra="forbid")  # Unknown fields are rejected with a 422.

    start: UtcTimestamp  # Inclusive start, normalized to UTC.
    end: UtcTimestamp  # Exclusive end, normalized to UTC.


class BlockOut(BaseModel):  # The created block.
    model_config = ConfigDict(from_attributes=True)  # Allow building this from an object's attributes.

    id: uuid.UUID  # The block's ID.
    field_id: uuid.UUID  # The blocked field.
    status: Literal["ACTIVE"] = "ACTIVE"  # A new block is always active.
    start: datetime  # Start of the block, in UTC.
    end: datetime  # End of the block, in UTC.
