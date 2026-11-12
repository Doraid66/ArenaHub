"""Add booking/block occupancy and durable retry receipts after Person 2's users."""

from alembic import op  # Alembic runs these schema changes in order.
import sqlalchemy as sa  # Explicit column types keep migrations independent of later model edits.

revision = "0003"  # Fixed team-assigned revision identifier.
down_revision = "0002"  # Users and manager memberships must exist first.
branch_labels = None  # Keep one linear migration history.
depends_on = None  # The previous revision already expresses the dependency.


def upgrade() -> None:  # Create both sides of the atomic booking/receipt write.
    op.create_table(  # One occupancy table supports the common conflict query.
        "reservations",  # Must match Reservation.__tablename__.
        sa.Column("id", sa.Uuid(), nullable=False),  # Application-generated UUID.
        sa.Column("field_id", sa.Uuid(), nullable=False),  # Existing catalog surface.
        sa.Column("user_id", sa.Uuid(), nullable=False),  # Existing authenticated owner.
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),  # PostgreSQL TIMESTAMPTZ.
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),  # Exclusive interval endpoint.
        sa.Column("kind", sa.String(16), nullable=False),  # BOOKING or BLOCK.
        sa.Column("status", sa.String(16), nullable=False),  # Kind-specific lifecycle state.
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),  # Blocks do not expire as holds.
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),  # Database audit timestamp.
        sa.PrimaryKeyConstraint("id", name="pk_reservations"),  # Explicit names simplify schema comparison.
        sa.ForeignKeyConstraint(["field_id"], ["fields.id"], name="fk_reservations_field_id_fields", ondelete="RESTRICT"),  # Preserve referenced catalog rows.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_reservations_user_id_users", ondelete="RESTRICT"),  # Preserve booking ownership.
        sa.CheckConstraint("end_at > start_at", name=op.f("ck_reservations_valid_interval")),  # op.f prevents a doubled naming-convention prefix.
        sa.CheckConstraint("kind IN ('BOOKING', 'BLOCK')", name=op.f("ck_reservations_valid_kind")),  # Reject unsupported kinds.
        sa.CheckConstraint(  # Keep the database state machine consistent with the service.
            "(kind = 'BOOKING' AND status IN ('HELD', 'CONFIRMED', 'CANCELLED', 'EXPIRED')) "  # Legal booking states.
            "OR (kind = 'BLOCK' AND status IN ('ACTIVE', 'CANCELLED'))",  # Legal block states.
            name=op.f("ck_reservations_valid_kind_status"),  # Already-expanded check name.
        ),  # Finish the state-machine constraint.
        sa.CheckConstraint("status <> 'HELD' OR hold_expires_at IS NOT NULL", name=op.f("ck_reservations_held_requires_expiry")),  # No immortal temporary holds.
    )  # Finish the reservation table.
    op.create_index("ix_reservations_field_interval", "reservations", ["field_id", "start_at", "end_at"])  # Accelerate overlap checks.
    op.create_index("ix_reservations_user_id", "reservations", ["user_id"])  # Index the owner foreign key.
    op.create_table(  # Receipts live in PostgreSQL, so every API instance sees retries.
        "idempotency_records",  # Must match IdempotencyRecord.__tablename__.
        sa.Column("id", sa.Uuid(), nullable=False),  # Internal receipt identifier.
        sa.Column("user_id", sa.Uuid(), nullable=False),  # Caller-scoped key namespace.
        sa.Column("operation", sa.String(40), nullable=False),  # Separate hold and block operations.
        sa.Column("key", sa.String(200), nullable=False),  # Validated opaque key.
        sa.Column("request_hash", sa.String(64), nullable=False),  # Canonical SHA-256 request digest.
        sa.Column("response_status", sa.Integer(), nullable=False),  # Store the original success code.
        sa.Column("response_body", sa.JSON(), nullable=False),  # Store the original response snapshot.
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_records"),  # Every receipt is uniquely addressable internally.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_idempotency_records_user_id_users", ondelete="RESTRICT"),  # A receipt belongs to a real user.
        sa.UniqueConstraint("user_id", "operation", "key", name="uq_idempotency_records_scoped_key"),  # Arbitrates simultaneous duplicate keys.
    )  # Finish the receipt table.


def downgrade() -> None:  # Run only on a disposable database: these tables contain booking data.
    op.drop_table("idempotency_records")  # Remove receipts before rolling back the reservation feature.
    op.drop_index("ix_reservations_user_id", table_name="reservations")  # Undo the owner lookup index.
    op.drop_index("ix_reservations_field_interval", table_name="reservations")  # Undo the overlap lookup index.
    op.drop_table("reservations")  # Leave Person 2's users and Person 3's catalog intact.
