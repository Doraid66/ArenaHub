"""Time-block request and response shapes agreed with the reservation engine."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.timestamps import UtcTimestamp


class BlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: UtcTimestamp
    end: UtcTimestamp


class BlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field_id: uuid.UUID
    status: Literal["ACTIVE"] = "ACTIVE"
    start: datetime
    end: datetime
