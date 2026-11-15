"""Run with the full suite once PostgreSQL/Docker is available."""

import pytest  # Parametrized tests.
from sqlalchemy import func, select  # Count rows.

from app.auth.demo_accounts import (  # Fixed demo IDs and emails.
    DEMO_MANAGER_EMAIL, DEMO_MANAGER_ID,  # The manager account.
    DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_1_ID, DEMO_PLAYER_2_EMAIL, DEMO_PLAYER_2_ID,  # The two player accounts.
)  # Finish the demo imports.
from app.auth.models import ManagerFacility, User  # Auth tables.
from app.auth.security import verify_password  # Check stored hashes.
from app.auth.seed import seed_accounts  # The seeding function under test.
from app.catalog.demo_data import DEMO_FACILITY_ID  # The manager's facility.
from app.core.config import get_settings  # Seed passwords.
from app.core.database import SessionLocal  # Open a real PostgreSQL session.


@pytest.mark.parametrize("email,password_setting,user_id", [  # One case per demo account.
    (DEMO_PLAYER_1_EMAIL, "seed_player_password", DEMO_PLAYER_1_ID),  # First player.
    (DEMO_PLAYER_2_EMAIL, "seed_player_password", DEMO_PLAYER_2_ID),  # Second player.
    (DEMO_MANAGER_EMAIL, "seed_manager_password", DEMO_MANAGER_ID),  # The manager.
])  # Finish the cases.
def test_seeded_account_can_log_in_on_postgres(anon_client, email, password_setting, user_id):  # Seeded users can really log in.
    response = anon_client.post("/auth/login", json={  # Real login request.
        "email": email, "password": getattr(get_settings(), password_setting),  # The seeded credentials.
    })  # Finish the request.
    assert response.status_code == 200  # Login succeeds.
    me = anon_client.get("/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})  # Use the token.
    assert me.status_code == 200  # The token works.
    assert me.json()["id"] == str(user_id)  # It belongs to the right account.


def test_seed_is_repeatable_and_stays_in_callers_transaction():  # Seeding twice is safe and never commits.
    with SessionLocal() as db:  # Open a real session.
        before_users = db.scalar(select(func.count()).select_from(User))  # User count before seeding.
        before_memberships = db.scalar(select(func.count()).select_from(ManagerFacility))  # Membership count before seeding.
        before_hash = db.get(User, DEMO_PLAYER_1_ID).password_hash  # Player 1's hash before seeding.
        seed_accounts(db)  # Seed once.
        seed_accounts(db)  # Seed again; must be harmless.
        db.expire_all()  # Force fresh reads below.
        assert db.in_transaction()  # Seeding left the transaction open.
        assert db.scalar(select(func.count()).select_from(User)) == before_users  # No duplicate users.
        assert db.scalar(select(func.count()).select_from(ManagerFacility)) == before_memberships  # No duplicate memberships.
        player1 = db.get(User, DEMO_PLAYER_1_ID)  # Reload player 1.
        player2 = db.get(User, DEMO_PLAYER_2_ID)  # Reload player 2.
        assert player1.password_hash != player2.password_hash  # Different salts give different hashes.
        assert player1.password_hash != before_hash  # Seeding refreshed the hash.
        assert verify_password(player1.password_hash, get_settings().seed_player_password)  # The new hash still matches the password.
        assert list(db.scalars(select(ManagerFacility.facility_id).where(  # The manager's facilities.
            ManagerFacility.user_id == DEMO_MANAGER_ID,  # Only this manager.
        ))) == [DEMO_FACILITY_ID]  # Exactly the demo facility.
        db.rollback()  # Undo everything the seeding did.
        assert db.get(User, DEMO_PLAYER_1_ID).password_hash == before_hash  # Proves nothing was committed.
