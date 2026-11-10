"""Seed demo accounts inside the caller's transaction; never commit here."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth.demo_accounts import (
    DEMO_MANAGER_EMAIL, DEMO_MANAGER_ID,
    DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_1_ID, DEMO_PLAYER_2_EMAIL, DEMO_PLAYER_2_ID,
)
from app.auth.models import ManagerFacility, User
from app.auth.security import hash_password
from app.catalog.demo_data import DEMO_FACILITY_ID
from app.core.config import get_settings


def seed_accounts(db: Session) -> None:
    settings = get_settings()
    for name, value in (
        ("SEED_PLAYER_PASSWORD", settings.seed_player_password),
        ("SEED_MANAGER_PASSWORD", settings.seed_manager_password),
    ):
        if not value:
            raise RuntimeError(f"Set {name} before seeding demo accounts")

    rows = [
        {"id": DEMO_PLAYER_1_ID, "email": DEMO_PLAYER_1_EMAIL,
         "password_hash": hash_password(settings.seed_player_password)},
        {"id": DEMO_PLAYER_2_ID, "email": DEMO_PLAYER_2_EMAIL,
         "password_hash": hash_password(settings.seed_player_password)},
        {"id": DEMO_MANAGER_ID, "email": DEMO_MANAGER_EMAIL,
         "password_hash": hash_password(settings.seed_manager_password)},
    ]
    statement = insert(User).values(rows)
    db.execute(statement.on_conflict_do_update(
        index_elements=["id"],
        set_={"email": statement.excluded.email, "password_hash": statement.excluded.password_hash},
    ))
    db.execute(insert(ManagerFacility).values(
        user_id=DEMO_MANAGER_ID, facility_id=DEMO_FACILITY_ID,
    ).on_conflict_do_nothing(index_elements=["user_id", "facility_id"]))
