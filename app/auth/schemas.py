"""Public authentication DTOs. Password hashes are never part of a response."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    # Refuse attempts to set an owner, ID, role, or membership through login input.
    model_config = ConfigDict(extra="forbid")

    # Explicitly exclude U+0085: Rust's runtime \s includes it, while OpenAPI's
    # ECMAScript \s does not. Both validators must agree on acceptable emails.
    email: str = Field(
        min_length=3, max_length=254,
        pattern=r"^[^@\s\x00\u0085]+@[^@\s\x00\u0085]+$", strict=True,
    )
    password: str = Field(min_length=1, max_length=1024, strict=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    managed_facility_ids: list[uuid.UUID]
