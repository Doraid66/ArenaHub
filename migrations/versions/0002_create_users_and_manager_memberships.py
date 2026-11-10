"""Create users and facility-manager memberships (Person 2).

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "manager_facilities",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "facility_id", name="pk_manager_facilities"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_manager_facilities_user_id_users", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"], ["facilities.id"],
            name="fk_manager_facilities_facility_id_facilities", ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_manager_facilities_facility_id", "manager_facilities", ["facility_id"])


def downgrade() -> None:
    op.drop_index("ix_manager_facilities_facility_id", table_name="manager_facilities")
    op.drop_table("manager_facilities")
    op.drop_table("users")
