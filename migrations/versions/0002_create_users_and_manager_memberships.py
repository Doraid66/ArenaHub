"""Create users and facility-manager memberships (Person 2).

Revision ID: 0002
Revises: 0001
"""

from alembic import op  # Alembic's schema-change operations.
import sqlalchemy as sa  # Column types and constraints.

revision = "0002"  # This migration's ID.
down_revision = "0001"  # Facilities must exist first.
branch_labels = None  # No branching.
depends_on = None  # No extra dependencies.


def upgrade() -> None:  # Apply this migration.
    op.create_table(  # Accounts.
        "users",  # Table name.
        sa.Column("id", sa.Uuid(), nullable=False),  # Primary key.
        sa.Column("email", sa.String(254), nullable=False),  # Login email.
        sa.Column("password_hash", sa.String(512), nullable=False),  # Argon2 hash.
        sa.PrimaryKeyConstraint("id", name="pk_users"),  # Named primary key.
        sa.UniqueConstraint("email", name="uq_users_email"),  # One account per email.
    )  # Finish the users table.
    op.create_table(  # Who manages which facility.
        "manager_facilities",  # Table name.
        sa.Column("user_id", sa.Uuid(), nullable=False),  # The manager.
        sa.Column("facility_id", sa.Uuid(), nullable=False),  # The facility they manage.
        sa.PrimaryKeyConstraint("user_id", "facility_id", name="pk_manager_facilities"),  # One row per pair.
        sa.ForeignKeyConstraint(  # Link to the user.
            ["user_id"], ["users.id"], name="fk_manager_facilities_user_id_users", ondelete="CASCADE",  # Deleting a user removes memberships.
        ),  # Finish the user link.
        sa.ForeignKeyConstraint(  # Link to the facility.
            ["facility_id"], ["facilities.id"],  # Column and the column it points to.
            name="fk_manager_facilities_facility_id_facilities", ondelete="RESTRICT",  # A facility with managers cannot be deleted.
        ),  # Finish the facility link.
    )  # Finish the memberships table.
    op.create_index("ix_manager_facilities_facility_id", "manager_facilities", ["facility_id"])  # Fast lookup by facility.


def downgrade() -> None:  # Undo this migration.
    op.drop_index("ix_manager_facilities_facility_id", table_name="manager_facilities")  # Remove the index first.
    op.drop_table("manager_facilities")  # Memberships depend on users.
    op.drop_table("users")  # Then users.
