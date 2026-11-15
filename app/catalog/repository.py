"""Database queries for facilities and fields. No business rules here."""

import uuid  # Field IDs are UUIDs.

from sqlalchemy import select  # Build SQL queries.
from sqlalchemy.orm import Session  # The request's database session.

from app.catalog.models import Field  # The fields table.


def list_fields(db: Session) -> list[Field]:  # Fetch every field in a friendly order.
    """All fields: grouped by facility, full/standalone fields before their sub-fields."""
    stmt = select(Field).order_by(  # Query all fields, sorted.
        Field.facility_id,  # Group fields by facility.
        Field.parent_field_id.is_not(None),  # False (no parent) sorts before True.
        Field.name,  # Alphabetical inside each group.
    )  # Finish the query.
    return list(db.scalars(stmt))  # Run it and return a plain list.


def get_field(db: Session, field_id: uuid.UUID) -> Field | None:  # Fetch one field.
    """One field by id, or None if it doesn't exist."""
    return db.get(Field, field_id)  # Primary-key lookup; None if missing.
