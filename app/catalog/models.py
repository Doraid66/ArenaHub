"""Database tables for the catalog: facilities and their fields."""

import uuid  # Rows are identified by UUIDs.

from sqlalchemy import (  # Column types and constraints.
    CheckConstraint,  # A rule checked by the database on every write.
    ForeignKey,  # A link to another table's row.
    ForeignKeyConstraint,  # A link made of several columns.
    String,  # Text column with a length limit.
    UniqueConstraint,  # No two rows may repeat these values.
    Uuid,  # UUID column type.
)  # Finish the SQLAlchemy imports.
from sqlalchemy.orm import Mapped, mapped_column  # Typed column declarations.

from app.core.database import Base  # The one base class every model shares.


class Facility(Base):  # A sports centre.
    """A sports centre, e.g. "Centre Multisports Demo"."""

    __tablename__ = "facilities"  # Table created by migration 0001.

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)  # Random UUID made in Python.
    name: Mapped[str] = mapped_column(String(200))  # Display name.


class Field(Base):  # A bookable surface.
    """A bookable surface. A full field may have direct sub-fields (parent_field_id set).

    Rules:
    - A sub-field must belong to the same facility as its parent (enforced by the database).
    - A field can't be its own parent (enforced by the database).
    - Only one level: a sub-field has no sub-fields of its own (enforced by the seed data;
      nested subdivisions are out of scope for this phase).
    """

    __tablename__ = "fields"  # Table created by migration 0001.

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)  # Random UUID made in Python.
    facility_id: Mapped[uuid.UUID] = mapped_column(  # The facility this field belongs to.
        Uuid, ForeignKey("facilities.id", ondelete="RESTRICT"), index=True  # A facility with fields cannot be deleted.
    )  # Finish facility_id.
    parent_field_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)  # Set only for sub-fields.
    name: Mapped[str] = mapped_column(String(200))  # Display name.
    sport: Mapped[str] = mapped_column(String(50))  # Sport played on this field.

    __table_args__ = (  # Table-level constraints.
        # Lets other rows refer to the pair (id, facility_id).
        UniqueConstraint("id", "facility_id", name="uq_fields_id_facility_id"),  # Needed for the same-facility link below.
        # The parent must be a field in the SAME facility: the pair
        # (parent_field_id, facility_id) must exist as (id, facility_id) in this table.
        ForeignKeyConstraint(  # Parent link that also checks the facility.
            ["parent_field_id", "facility_id"],  # Columns on this row.
            ["fields.id", "fields.facility_id"],  # Must match a parent's id and facility.
            name="fk_fields_parent_same_facility",  # Explicit constraint name.
            ondelete="RESTRICT",  # A parent with sub-fields cannot be deleted.
        ),  # Finish the parent link.
        CheckConstraint(  # Rule checked on every write.
            "parent_field_id IS NULL OR parent_field_id <> id",  # A field cannot be its own parent.
            name="not_own_parent",  # Base adds the ck_fields_ prefix.
        ),  # Finish the check.
    )  # Finish the constraints.
