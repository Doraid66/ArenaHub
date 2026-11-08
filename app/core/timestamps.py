"""Shared timestamp type for every endpoint that receives a date-time.

    from app.core.timestamps import UtcTimestamp

    class HoldRequest(BaseModel):
        start: UtcTimestamp
        end: UtcTimestamp

Accepts only ISO 8601 text WITH a timezone offset (e.g. 2026-11-15T20:00:00-05:00 or
...Z) and converts it to UTC. Rejects, with a 422 in the shared error format:
naive times (no offset), bare dates, numbers like 0 or 1700000000 (which Pydantic would
otherwise read as Unix timestamps), and dates that can't be represented in UTC.
"""

import re
from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator

EXAMPLE = "2026-11-15T20:00:00-05:00"

_ISO_WITH_OFFSET = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([Zz]|[+-]\d{2}:\d{2})$"
)


def _require_iso_text_with_offset(value: Any) -> Any:
    if isinstance(value, datetime):  # already a datetime (e.g. built in Python code)
        return value
    if not isinstance(value, str) or not _ISO_WITH_OFFSET.match(value):
        raise ValueError(f"must be an ISO 8601 date-time with a timezone offset, e.g. {EXAMPLE}")
    return value


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"must include a timezone offset, e.g. {EXAMPLE}")
    try:
        return value.astimezone(timezone.utc)
    except OverflowError:
        # e.g. 0001-01-01T00:00:01+00:03 would fall before year 1 in UTC
        raise ValueError("is out of range") from None


UtcTimestamp = Annotated[
    datetime,
    BeforeValidator(_require_iso_text_with_offset),
    AfterValidator(_to_utc),
]