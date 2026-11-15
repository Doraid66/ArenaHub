"""Public authentication DTOs. Password hashes are never part of a response."""

import uuid  # IDs are UUIDs.
from typing import Literal  # Restrict a field to one exact value.

from pydantic import BaseModel, ConfigDict, Field  # Validated request and response models.


class LoginRequest(BaseModel):  # The body of POST /auth/login.
    # Refuse attempts to set an owner, ID, role, or membership through login input.
    model_config = ConfigDict(extra="forbid")  # Any unknown field is rejected with a 422.

    # Explicitly exclude U+0085: Rust's runtime \s includes it, while OpenAPI's
    # ECMAScript \s does not. Both validators must agree on acceptable emails.
    email: str = Field(  # The login email.
        min_length=3, max_length=254,  # Shortest and longest valid email.
        pattern=r"^[^@\s\x00\u0085]+@[^@\s\x00\u0085]+$", strict=True,  # One @, no whitespace, no NUL; strings only.
    )  # Finish the email field.
    password: str = Field(min_length=1, max_length=1024, strict=True)  # Required, bounded, and must be a string.


class TokenOut(BaseModel):  # The login response.
    access_token: str  # The signed JWT.
    token_type: Literal["bearer"] = "bearer"  # Always "bearer".
    expires_in: int  # Seconds until the token expires.


class UserOut(BaseModel):  # The /auth/me response.
    id: uuid.UUID  # The user's ID.
    email: str  # The user's login email.
    managed_facility_ids: list[uuid.UUID]  # Facilities this user manages (empty for players).
