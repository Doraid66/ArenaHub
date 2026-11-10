"""Users and facility memberships, using the application's shared SQLAlchemy Base."""

import uuid

from sqlalchemy import ForeignKey, PrimaryKeyConstraint, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(512))

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_users"),
        UniqueConstraint("email", name="uq_users_email"),
    )


class ManagerFacility(Base):
    """A membership grants authority for exactly one facility; there is no global role."""

    __tablename__ = "manager_facilities"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", name="fk_manager_facilities_user_id_users", ondelete="CASCADE")
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("facilities.id", name="fk_manager_facilities_facility_id_facilities", ondelete="RESTRICT"),
        index=True,
    )

    __table_args__ = (PrimaryKeyConstraint("user_id", "facility_id", name="pk_manager_facilities"),)
