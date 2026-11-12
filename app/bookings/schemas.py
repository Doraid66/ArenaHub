"""Public booking shapes used by FastAPI and the generated OpenAPI contract."""

from datetime import datetime  # Responses contain aware UTC datetimes.
from typing import Literal  # Restrict the public booking states.
from uuid import UUID  # Expose UUIDs rather than sequential counters.

from pydantic import BaseModel, ConfigDict  # Validate request and response objects.

from app.core.timestamps import UtcTimestamp  # Reuse strict offset-aware parsing.


class HoldRequest(BaseModel):  # Caller identity is deliberately absent.
    model_config = ConfigDict(extra="forbid")  # Reject forged user_id, status, or expiry fields.

    start: UtcTimestamp  # Inclusive start, normalized to UTC.
    end: UtcTimestamp  # Exclusive end; the service checks end > start.


class BookingResponse(BaseModel):  # The exact shape expected by the existing test frontend.
    id: UUID  # Used for subsequent reads and cancellation.
    field_id: UUID  # Identifies the reserved field or sub-field.
    status: Literal["HELD", "CONFIRMED", "CANCELLED", "EXPIRED"]  # Effective state at the time of this response.
    start: datetime  # UTC playing-interval start.
    end: datetime  # UTC playing-interval end.
    hold_expires_at: datetime | None  # A temporary hold has a server-owned deadline.
