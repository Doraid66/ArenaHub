"""Database tables for the catalog: facilities and their fields."""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Facility(Base):
    """A sports centre, e.g. "Centre Multisports Demo"."""

    __tablename__ = "facilities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))


class Field(Base):
    """A bookable surface. A full field may have direct sub-fields (parent_field_id set).

    Rules:
    - A sub-field must belong to the same facility as its parent (enforced by the database).
    - A field can't be its own parent (enforced by the database).
    - Only one level: a sub-field has no sub-fields of its own (enforced by the seed data;
      nested subdivisions are out of scope for this phase).
    """

    __tablename__ = "fields"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("facilities.id", ondelete="RESTRICT"), index=True
    )
    parent_field_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(200))
    sport: Mapped[str] = mapped_column(String(50))

    __table_args__ = (
        # Lets other rows refer to the pair (id, facility_id).
        UniqueConstraint("id", "facility_id", name="uq_fields_id_facility_id"),
        # The parent must be a field in the SAME facility: the pair
        # (parent_field_id, facility_id) must exist as (id, facility_id) in this table.
        ForeignKeyConstraint(
            ["parent_field_id", "facility_id"],
            ["fields.id", "fields.facility_id"],
            name="fk_fields_parent_same_facility",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "parent_field_id IS NULL OR parent_field_id <> id",
            name="not_own_parent",
        ),
    )