"""Users and facility memberships, using the application's shared SQLAlchemy Base."""

import uuid  # Users are identified by UUIDs.

from sqlalchemy import ForeignKey, PrimaryKeyConstraint, String, UniqueConstraint, Uuid  # Column types and table constraints.
from sqlalchemy.orm import Mapped, mapped_column  # Typed column declarations.

from app.core.database import Base  # The one base class every model shares.


class User(Base):  # One row per account.
    __tablename__ = "users"  # Table created by migration 0002.

    id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4)  # Random UUID made in Python.
    email: Mapped[str] = mapped_column(String(254))  # Login name; 254 is the longest valid email.
    password_hash: Mapped[str] = mapped_column(String(512))  # Argon2 hash, never the plain password.

    __table_args__ = (  # Table-level constraints.
        PrimaryKeyConstraint("id", name="pk_users"),  # Named primary key on id.
        UniqueConstraint("email", name="uq_users_email"),  # Two accounts cannot share an email.
    )  # Finish the constraints.


class ManagerFacility(Base):  # Links a manager to a facility.
    """A membership grants authority for exactly one facility; there is no global role."""

    __tablename__ = "manager_facilities"  # Table created by migration 0002.

    user_id: Mapped[uuid.UUID] = mapped_column(  # The manager's account.
        Uuid, ForeignKey("users.id", name="fk_manager_facilities_user_id_users", ondelete="CASCADE")  # Deleting a user removes their memberships.
    )  # Finish user_id.
    facility_id: Mapped[uuid.UUID] = mapped_column(  # The facility they manage.
        Uuid,  # Same type as facilities.id.
        ForeignKey("facilities.id", name="fk_manager_facilities_facility_id_facilities", ondelete="RESTRICT"),  # A facility with managers cannot be deleted.
        index=True,  # Fast lookup of managers by facility.
    )  # Finish facility_id.

    __table_args__ = (PrimaryKeyConstraint("user_id", "facility_id", name="pk_manager_facilities"),)  # One membership per user and facility.
