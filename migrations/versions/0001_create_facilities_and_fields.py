"""create facilities and fields

Revision ID: 0001
Revises:
Create Date: 2026-11-07

Person 3 (catalog). Must match app/catalog/models.py exactly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the facilities and fields tables."""
    op.create_table(
        "facilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_facilities"),
    )

    op.create_table(
        "fields",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("parent_field_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sport", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fields"),
        sa.ForeignKeyConstraint(
            ["facility_id"], ["facilities.id"],
            name="fk_fields_facility_id_facilities", ondelete="RESTRICT",
        ),
        # Needed so a sub-field can point to (parent id, same facility id).
        sa.UniqueConstraint("id", "facility_id", name="uq_fields_id_facility_id"),
        # A sub-field's parent must be in the same facility.
        sa.ForeignKeyConstraint(
            ["parent_field_id", "facility_id"], ["fields.id", "fields.facility_id"],
            name="fk_fields_parent_same_facility", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "parent_field_id IS NULL OR parent_field_id <> id",
            # op.f() = "use this exact name": stops the naming convention adding a second "ck_fields_" prefix.
            name=op.f("ck_fields_not_own_parent"),
        ),
    )
    op.create_index("ix_fields_facility_id", "fields", ["facility_id"])
    op.create_index("ix_fields_parent_field_id", "fields", ["parent_field_id"])


def downgrade() -> None:
    """Remove the tables, in reverse order (fields depend on facilities)."""
    op.drop_index("ix_fields_parent_field_id", table_name="fields")
    op.drop_index("ix_fields_facility_id", table_name="fields")
    op.drop_table("fields")
    op.drop_table("facilities")