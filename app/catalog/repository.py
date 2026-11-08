"""Database queries for facilities and fields. No business rules here."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import Field


def list_fields(db: Session) -> list[Field]:
    """All fields: grouped by facility, full/standalone fields before their sub-fields."""
    stmt = select(Field).order_by(
        Field.facility_id,
        Field.parent_field_id.is_not(None),  # False (no parent) sorts before True
        Field.name,
    )
    return list(db.scalars(stmt))


def get_field(db: Session, field_id: uuid.UUID) -> Field | None:
    """One field by id, or None if it doesn't exist."""
    return db.get(Field, field_id)