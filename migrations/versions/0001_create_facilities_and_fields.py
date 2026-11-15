"""create facilities and fields

Revision ID: 0001
Revises:
Create Date: 2026-11-07

Person 3 (catalog). Must match app/catalog/models.py exactly.
"""
from typing import Sequence, Union  # Type hints for the revision identifiers.

from alembic import op  # Alembic's schema-change operations.
import sqlalchemy as sa  # Column types and constraints.


# revision identifiers, used by Alembic.
revision: str = "0001"  # This migration's ID.
down_revision: Union[str, Sequence[str], None] = None  # First migration: nothing comes before it.
branch_labels: Union[str, Sequence[str], None] = None  # No branching.
depends_on: Union[str, Sequence[str], None] = None  # No extra dependencies.


def upgrade() -> None:  # Apply this migration.
    """Create the facilities and fields tables."""
    op.create_table(  # Facilities come first.
        "facilities",  # Table name.
        sa.Column("id", sa.Uuid(), nullable=False),  # Primary key.
        sa.Column("name", sa.String(length=200), nullable=False),  # Display name.
        sa.PrimaryKeyConstraint("id", name="pk_facilities"),  # Named primary key.
    )  # Finish the facilities table.

    op.create_table(  # Fields depend on facilities.
        "fields",  # Table name.
        sa.Column("id", sa.Uuid(), nullable=False),  # Primary key.
        sa.Column("facility_id", sa.Uuid(), nullable=False),  # The owning facility.
        sa.Column("parent_field_id", sa.Uuid(), nullable=True),  # Set only for sub-fields.
        sa.Column("name", sa.String(length=200), nullable=False),  # Display name.
        sa.Column("sport", sa.String(length=50), nullable=False),  # Sport played here.
        sa.PrimaryKeyConstraint("id", name="pk_fields"),  # Named primary key.
        sa.ForeignKeyConstraint(  # Link to the facility.
            ["facility_id"], ["facilities.id"],  # Column and the column it points to.
            name="fk_fields_facility_id_facilities", ondelete="RESTRICT",  # A facility with fields cannot be deleted.
        ),  # Finish the facility link.
        # Needed so a sub-field can point to (parent id, same facility id).
        sa.UniqueConstraint("id", "facility_id", name="uq_fields_id_facility_id"),  # Makes the pair referenceable.
        # A sub-field's parent must be in the same facility.
        sa.ForeignKeyConstraint(  # Link to the parent field.
            ["parent_field_id", "facility_id"], ["fields.id", "fields.facility_id"],  # Parent must share the facility.
            name="fk_fields_parent_same_facility", ondelete="RESTRICT",  # A parent with sub-fields cannot be deleted.
        ),  # Finish the parent link.
        sa.CheckConstraint(  # Rule checked on every write.
            "parent_field_id IS NULL OR parent_field_id <> id",  # A field cannot be its own parent.
            # op.f() = "use this exact name": stops the naming convention adding a second "ck_fields_" prefix.
            name=op.f("ck_fields_not_own_parent"),  # Already-expanded constraint name.
        ),  # Finish the check.
    )  # Finish the fields table.
    op.create_index("ix_fields_facility_id", "fields", ["facility_id"])  # Fast lookup by facility.
    op.create_index("ix_fields_parent_field_id", "fields", ["parent_field_id"])  # Fast lookup of sub-fields.


def downgrade() -> None:  # Undo this migration.
    """Remove the tables, in reverse order (fields depend on facilities)."""
    op.drop_index("ix_fields_parent_field_id", table_name="fields")  # Remove the parent index.
    op.drop_index("ix_fields_facility_id", table_name="fields")  # Remove the facility index.
    op.drop_table("fields")  # Fields first, because they depend on facilities.
    op.drop_table("facilities")  # Then facilities.
