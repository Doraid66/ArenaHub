"""Small reservation rules, with no HTTP handling or database queries."""

import hashlib  # A fixed-size digest makes request comparisons inexpensive.
import json  # Canonical JSON gives the digest a stable input.
from datetime import datetime, timezone  # Compare instants in UTC.
from uuid import UUID  # Field identifiers are UUIDs.

from pydantic import TypeAdapter, ValidationError  # Reuse the shared timestamp validator for direct service calls.

from app.core.errors import InvalidInputError  # Service callers receive the shared domain error.
from app.core.timestamps import UtcTimestamp  # The existing validator handles offsets and date overflows.

_timestamp = TypeAdapter(UtcTimestamp)  # Build the reusable adapter once.


def normalize_interval(start: datetime, end: datetime) -> tuple[datetime, datetime]:  # Direct Python callers get the same rules as HTTP callers.
    try:  # Convert valid offset-aware inputs to UTC.
        start = _timestamp.validate_python(start)  # Validate the inclusive start.
        end = _timestamp.validate_python(end)  # Validate the exclusive end.
    except ValidationError:  # Keep Pydantic details out of the service interface.
        raise InvalidInputError("Times must include a valid timezone offset") from None  # Return the established 422 error.
    if end <= start:  # Equal endpoints would reserve no time.
        raise InvalidInputError("'end' must be after 'start'")  # This cross-field rule cannot be expressed by OpenAPI alone.
    return start, end  # Both timestamps are now comparable UTC instants.


def validate_key(key: str) -> None:  # Internal callers must obey the same header contract.
    if not isinstance(key, str) or not 1 <= len(key) <= 200 or not all(33 <= ord(char) <= 126 for char in key):  # Visible ASCII only, matching Person 2.
        raise InvalidInputError("Idempotency-Key must contain 1 to 200 visible ASCII characters")  # Never let an invalid key reach a database column.


def validate_future_start(start: datetime, now: datetime) -> None:  # Call only after checking for an existing receipt.
    if start <= now:  # A new reservation must start in the future.
        raise InvalidInputError("'start' must be in the future")  # A replay is exempt because it creates nothing.


def effective_status(status: str, hold_expires_at: datetime | None, now: datetime) -> str:  # Compute expiry without needing a cleanup worker.
    if status == "HELD" and hold_expires_at is not None and hold_expires_at <= now:  # The deadline itself is already expired.
        return "EXPIRED"  # Reads and cancellation agree about elapsed holds.
    return status  # Confirmed, cancelled, and block states stay unchanged.


def request_fingerprint(field_id: UUID, start: datetime, end: datetime) -> str:  # Equivalent offsets must produce the same receipt lookup.
    payload = {  # Include every capacity-changing input.
        "field_id": str(field_id),  # A changed surface must reject key reuse.
        "start": start.astimezone(timezone.utc).isoformat(),  # Offset spelling must not affect identity.
        "end": end.astimezone(timezone.utc).isoformat(),  # The exclusive endpoint is part of the request too.
    }  # A stable dictionary becomes canonical JSON below.
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))  # Ignore dictionary ordering and whitespace.
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()  # Store only the digest, never log the request.
