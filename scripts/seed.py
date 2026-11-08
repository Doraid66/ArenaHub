"""Load demo data: facilities and fields (Person 3), then accounts (Person 2's hook).

Run from the project root:  python -m scripts.seed
Safe to run on every start-up: rows are inserted, or updated if they already exist,
so running it twice never creates duplicates.
"""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.catalog.demo_data import FACILITIES, FIELDS
from app.catalog.models import Facility, Field
from app.core.database import SessionLocal


def upsert(db: Session, model, rows: list[dict]) -> None:
    """INSERT the rows; if a row with the same id exists, UPDATE it instead."""
    stmt = insert(model).values(rows)
    columns_to_update = {name: stmt.excluded[name] for name in rows[0] if name != "id"}
    db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=columns_to_update))


def seed_accounts_if_available(db: Session) -> None:
    """Person 2 provides app/auth/seed.py with seed_accounts(db). Skip it until it exists."""
    try:
        from app.auth.seed import seed_accounts
    except ModuleNotFoundError as exc:
        if exc.name in ("app.auth", "app.auth.seed"):
            print("  accounts: skipped (app.auth.seed not available yet)")
            return
        raise  # app.auth.seed exists but has a broken import: show the real error
    seed_accounts(db)
    print("  accounts: loaded")


def main() -> None:
    # One transaction: either everything is loaded, or nothing is.
    with SessionLocal() as db, db.begin():
        upsert(db, Facility, FACILITIES)
        upsert(db, Field, FIELDS)
        print(f"  catalog: {len(FACILITIES)} facilities, {len(FIELDS)} fields")
        seed_accounts_if_available(db)
    print("Demo data ready.")


if __name__ == "__main__":
    main()