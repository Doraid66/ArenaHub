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

import re  # Pattern-match the timestamp text.
from datetime import datetime, timezone  # Work with timestamps and UTC.
from typing import Annotated, Any  # Attach validators to a type.

from pydantic import AfterValidator, BeforeValidator  # Run checks before and after parsing.

EXAMPLE = "2026-11-15T20:00:00-05:00"  # Sample value used in error messages.

_ISO_WITH_OFFSET = re.compile(  # Text must look like ISO 8601 with an offset.
    r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([Zz]|[+-]\d{2}:\d{2})$"  # Date, time, optional seconds, then Z or +/-HH:MM.
)  # Finish the pattern.


def _require_iso_text_with_offset(value: Any) -> Any:  # Runs before Pydantic parses the value.
    if isinstance(value, datetime):  # Already a datetime (e.g. built in Python code).
        return value  # Checked later by the after-validator.
    if not isinstance(value, str) or not _ISO_WITH_OFFSET.match(value):  # Not text, or the wrong format.
        raise ValueError(f"must be an ISO 8601 date-time with a timezone offset, e.g. {EXAMPLE}")  # Reject numbers and naive times.
    return value  # Looks right; let Pydantic parse it.


def _to_utc(value: datetime) -> datetime:  # Runs after Pydantic parses the value.
    if value.tzinfo is None or value.utcoffset() is None:  # No timezone offset.
        raise ValueError(f"must include a timezone offset, e.g. {EXAMPLE}")  # Never guess a timezone.
    try:  # Conversion can overflow for extreme dates.
        return value.astimezone(timezone.utc)  # Same instant, expressed in UTC.
    except OverflowError:  # The UTC value would fall outside the supported range.
        # e.g. 0001-01-01T00:00:01+00:03 would fall before year 1 in UTC
        raise ValueError("is out of range") from None  # Return a 422 instead of a 500.


UtcTimestamp = Annotated[  # The type other modules import.
    datetime,  # Parsed as a normal datetime.
    BeforeValidator(_require_iso_text_with_offset),  # First: strict text check.
    AfterValidator(_to_utc),  # Last: convert to UTC.
]  # Finish the type.
