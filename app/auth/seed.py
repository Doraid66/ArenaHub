"""Seed demo accounts inside the caller's transaction; never commit here."""

from sqlalchemy.dialects.postgresql import insert  # PostgreSQL INSERT with ON CONFLICT support.
from sqlalchemy.orm import Session  # The caller's database session.

from app.auth.demo_accounts import (  # Fixed demo IDs and emails.
    DEMO_MANAGER_EMAIL, DEMO_MANAGER_ID,  # The manager account.
    DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_1_ID, DEMO_PLAYER_2_EMAIL, DEMO_PLAYER_2_ID,  # The two player accounts.
)  # Finish the demo imports.
from app.auth.models import ManagerFacility, User  # Tables being seeded.
from app.auth.security import hash_password  # Hash the seed passwords.
from app.catalog.demo_data import DEMO_FACILITY_ID  # The facility the manager runs.
from app.core.config import get_settings  # Seed passwords come from settings.


def seed_accounts(db: Session) -> None:  # Insert or refresh the demo users.
    settings = get_settings()  # Read the seed passwords.
    for name, value in (  # Check both passwords before writing anything.
        ("SEED_PLAYER_PASSWORD", settings.seed_player_password),  # Password for both players.
        ("SEED_MANAGER_PASSWORD", settings.seed_manager_password),  # Password for the manager.
    ):  # Finish the list of required settings.
        if not value:  # Missing or empty.
            raise RuntimeError(f"Set {name} before seeding demo accounts")  # Fail clearly, before any write.

    rows = [  # One dictionary per demo user.
        {"id": DEMO_PLAYER_1_ID, "email": DEMO_PLAYER_1_EMAIL,  # First player.
         "password_hash": hash_password(settings.seed_player_password)},  # Hash of the player password.
        {"id": DEMO_PLAYER_2_ID, "email": DEMO_PLAYER_2_EMAIL,  # Second player.
         "password_hash": hash_password(settings.seed_player_password)},  # Same password, different salt.
        {"id": DEMO_MANAGER_ID, "email": DEMO_MANAGER_EMAIL,  # The manager.
         "password_hash": hash_password(settings.seed_manager_password)},  # Hash of the manager password.
    ]  # Finish the rows.
    statement = insert(User).values(rows)  # One INSERT for all three users.
    db.execute(statement.on_conflict_do_update(  # Update the user if the ID already exists.
        index_elements=["id"],  # Conflict is detected on the primary key.
        set_={"email": statement.excluded.email, "password_hash": statement.excluded.password_hash},  # Overwrite with the new values.
    ))  # Finish the user upsert.
    db.execute(insert(ManagerFacility).values(  # Make the manager a manager of the demo facility.
        user_id=DEMO_MANAGER_ID, facility_id=DEMO_FACILITY_ID,  # The membership pair.
    ).on_conflict_do_nothing(index_elements=["user_id", "facility_id"]))  # Running twice adds no duplicate.
