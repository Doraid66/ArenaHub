"""Load demo data: facilities and fields (Person 3), then accounts (Person 2's hook).

Run from the project root:  python -m scripts.seed
Safe to run on every start-up: rows are inserted, or updated if they already exist,
so running it twice never creates duplicates.
"""

from sqlalchemy.dialects.postgresql import insert  # PostgreSQL INSERT with ON CONFLICT support.
from sqlalchemy.orm import Session  # A database session.

from app.catalog.demo_data import FACILITIES, FIELDS  # The fixed demo rows.
from app.catalog.models import Facility, Field  # Tables being seeded.
from app.core.database import SessionLocal  # Opens a session.


def upsert(db: Session, model, rows: list[dict]) -> None:  # Insert rows, or update ones that exist.
    """INSERT the rows; if a row with the same id exists, UPDATE it instead."""
    stmt = insert(model).values(rows)  # One INSERT for all rows.
    columns_to_update = {name: stmt.excluded[name] for name in rows[0] if name != "id"}  # Refresh every column except the ID.
    db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=columns_to_update))  # On a duplicate ID, update instead.


def seed_accounts_if_available(db: Session) -> None:  # Seed users when the auth module exists.
    """Person 2 provides app/auth/seed.py with seed_accounts(db). Skip it until it exists."""
    try:  # The auth module may not exist yet.
        from app.auth.seed import seed_accounts  # Import late, only when needed.
    except ModuleNotFoundError as exc:  # The import failed.
        if exc.name in ("app.auth", "app.auth.seed"):  # The auth seed itself is missing.
            print("  accounts: skipped (app.auth.seed not available yet)")  # Tell the user and carry on.
            return  # Nothing more to do.
        raise  # app.auth.seed exists but has a broken import: show the real error.
    seed_accounts(db)  # Insert or refresh the demo users.
    print("  accounts: loaded")  # Confirm to the user.


def main() -> None:  # Entry point.
    # One transaction: either everything is loaded, or nothing is.
    with SessionLocal() as db, db.begin():  # Open a session and commit at the end.
        upsert(db, Facility, FACILITIES)  # Load the facilities.
        upsert(db, Field, FIELDS)  # Load the fields.
        print(f"  catalog: {len(FACILITIES)} facilities, {len(FIELDS)} fields")  # Report what was loaded.
        seed_accounts_if_available(db)  # Load the demo users too.
    print("Demo data ready.")  # Everything was committed.


if __name__ == "__main__":  # Run only as a script.
    main()  # Start seeding.
