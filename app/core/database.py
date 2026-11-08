"""Database connection, the shared model Base, and per-request sessions."""

from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

# Consistent names for keys, indexes and constraints, so every team's
# migrations generate predictable names (e.g. "fk_fields_facility_id_facilities").
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """The ONE base class every model in the project inherits from."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# The engine manages a pool of connections to PostgreSQL.
# pool_pre_ping checks a connection is still alive before using it.
# connect_timeout: give up after 5 seconds if the database can't be reached, instead of hanging.
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)

# A factory that creates new Session objects.
# autoflush=False: nothing is sent to the database until we decide.
# expire_on_commit=False: objects stay readable after commit (handy for building responses).
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: give each request its own session, and always clean up.

    This does NOT commit. Services that write data commit or roll back themselves.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()