"""Account queries only; authentication and authorization rules live in services."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import ManagerFacility, User


def get_user(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def managed_facility_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.scalars(
        select(ManagerFacility.facility_id)
        .where(ManagerFacility.user_id == user_id)
        .order_by(ManagerFacility.facility_id)
    ))


def has_manager_membership(db: Session, user_id: uuid.UUID, facility_id: uuid.UUID) -> bool:
    return db.scalar(select(ManagerFacility.user_id).where(
        ManagerFacility.user_id == user_id,
        ManagerFacility.facility_id == facility_id,
    )) is not None
