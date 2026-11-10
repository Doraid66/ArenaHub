"""Run with the full suite once PostgreSQL/Docker is available."""

import pytest
from sqlalchemy import func, select

from app.auth.demo_accounts import (
    DEMO_MANAGER_EMAIL, DEMO_MANAGER_ID,
    DEMO_PLAYER_1_EMAIL, DEMO_PLAYER_1_ID, DEMO_PLAYER_2_EMAIL, DEMO_PLAYER_2_ID,
)
from app.auth.models import ManagerFacility, User
from app.auth.security import verify_password
from app.auth.seed import seed_accounts
from app.catalog.demo_data import DEMO_FACILITY_ID
from app.core.config import get_settings
from app.core.database import SessionLocal


@pytest.mark.parametrize("email,password_setting,user_id", [
    (DEMO_PLAYER_1_EMAIL, "seed_player_password", DEMO_PLAYER_1_ID),
    (DEMO_PLAYER_2_EMAIL, "seed_player_password", DEMO_PLAYER_2_ID),
    (DEMO_MANAGER_EMAIL, "seed_manager_password", DEMO_MANAGER_ID),
])
def test_seeded_account_can_log_in_on_postgres(anon_client, email, password_setting, user_id):
    response = anon_client.post("/auth/login", json={
        "email": email, "password": getattr(get_settings(), password_setting),
    })
    assert response.status_code == 200
    me = anon_client.get("/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == str(user_id)


def test_seed_is_repeatable_and_stays_in_callers_transaction():
    with SessionLocal() as db:
        before_users = db.scalar(select(func.count()).select_from(User))
        before_memberships = db.scalar(select(func.count()).select_from(ManagerFacility))
        before_hash = db.get(User, DEMO_PLAYER_1_ID).password_hash
        seed_accounts(db)
        seed_accounts(db)
        db.expire_all()
        assert db.in_transaction()
        assert db.scalar(select(func.count()).select_from(User)) == before_users
        assert db.scalar(select(func.count()).select_from(ManagerFacility)) == before_memberships
        player1 = db.get(User, DEMO_PLAYER_1_ID)
        player2 = db.get(User, DEMO_PLAYER_2_ID)
        assert player1.password_hash != player2.password_hash
        assert player1.password_hash != before_hash
        assert verify_password(player1.password_hash, get_settings().seed_player_password)
        assert list(db.scalars(select(ManagerFacility.facility_id).where(
            ManagerFacility.user_id == DEMO_MANAGER_ID,
        ))) == [DEMO_FACILITY_ID]
        db.rollback()
        assert db.get(User, DEMO_PLAYER_1_ID).password_hash == before_hash
