"""Database connection, the shared model Base, and per-request sessions."""

from collections.abc import Iterator  # Type for a generator that yields values.

from sqlalchemy import MetaData, create_engine  # Naming rules and the connection engine.
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker  # Model base class and session tools.

from app.core.config import get_settings  # Database URL comes from settings.

# Consistent names for keys, indexes and constraints, so every team's
# migrations generate predictable names (e.g. "fk_fields_facility_id_facilities").
NAMING_CONVENTION = {  # Patterns used to name constraints automatically.
    "ix": "ix_%(column_0_label)s",  # Index names.
    "uq": "uq_%(table_name)s_%(column_0_name)s",  # Unique constraint names.
    "ck": "ck_%(table_name)s_%(constraint_name)s",  # Check constraint names.
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",  # Foreign key names.
    "pk": "pk_%(table_name)s",  # Primary key names.
}  # Finish the naming patterns.


class Base(DeclarativeBase):  # Parent of every database model.
    """The ONE base class every model in the project inherits from."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)  # Apply the naming patterns to every table.


# The engine manages a pool of connections to PostgreSQL.
# pool_pre_ping checks a connection is still alive before using it.
# connect_timeout: give up after 5 seconds if the database can't be reached, instead of hanging.
engine = create_engine(  # One engine for the whole app.
    get_settings().database_url,  # Where the database lives.
    pool_pre_ping=True,  # Test each connection before using it.
    connect_args={"connect_timeout": 5},  # Fail after 5 seconds instead of hanging.
)  # Finish the engine.

# A factory that creates new Session objects.
# autoflush=False: nothing is sent to the database until we decide.
# expire_on_commit=False: objects stay readable after commit (handy for building responses).
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)  # Creates a fresh session on demand.


def get_db() -> Iterator[Session]:  # FastAPI calls this once per request.
    """FastAPI dependency: give each request its own session, and always clean up.

    This does NOT commit. Services that write data commit or roll back themselves.
    """
    db = SessionLocal()  # Open a new session.
    try:  # Hand it to the request.
        yield db  # The route runs while we wait here.
    except Exception:  # The request failed.
        db.rollback()  # Discard any half-finished changes.
        raise  # Let the error handlers deal with it.
    finally:  # Runs on success and on failure.
        db.close()  # Always release the connection.
