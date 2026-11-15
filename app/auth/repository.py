"""Account queries only; authentication and authorization rules live in services."""

import uuid  # IDs are UUIDs.

from sqlalchemy import select  # Build SQL queries.
from sqlalchemy.orm import Session  # The request's database session.

from app.auth.models import ManagerFacility, User  # The two account tables.


def get_user(db: Session, user_id: uuid.UUID) -> User | None:  # Find an account by its ID.
    return db.get(User, user_id)  # Primary-key lookup; None if it does not exist.


def get_user_by_email(db: Session, email: str) -> User | None:  # Find an account by its login email.
    return db.scalar(select(User).where(User.email == email))  # First match, or None.


def managed_facility_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:  # List the facilities a user manages.
    return list(db.scalars(  # Turn the result into a plain list.
        select(ManagerFacility.facility_id)  # Only the facility IDs are needed.
        .where(ManagerFacility.user_id == user_id)  # Memberships of this user only.
        .order_by(ManagerFacility.facility_id)  # Stable order for predictable responses.
    ))  # Finish the query and the list.


def has_manager_membership(db: Session, user_id: uuid.UUID, facility_id: uuid.UUID) -> bool:  # Is this user a manager of this facility?
    return db.scalar(select(ManagerFacility.user_id).where(  # Look for one matching membership row.
        ManagerFacility.user_id == user_id,  # Same user.
        ManagerFacility.facility_id == facility_id,  # Same facility.
    )) is not None  # A row means the user is a manager there.
