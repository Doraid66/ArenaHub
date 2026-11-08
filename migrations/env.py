"""Alembic environment: connects migrations to our settings and our shared Base."""

import importlib
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.core.database import Base

config = context.config

# Use the logging setup from alembic.ini when running the alembic command.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import every module that defines models, so Base.metadata knows all tables.
# Modules that don't exist yet on this branch are skipped.
MODEL_MODULES = [
    "app.catalog.models",       # Person 3: facilities, fields
    "app.auth.models",          # Person 2: users, manager_facilities
    "app.reservations.models",  # Person 1: reservations, idempotency_records
]
for module_name in MODEL_MODULES:
    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        # Skip only if THIS module (or its package) is missing. Any other missing
        # import means the module exists but is broken, so show the real error.
        if not (module_name == exc.name or module_name.startswith(f"{exc.name}.")):
            raise

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Print the SQL instead of running it (alembic upgrade head --sql)."""
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and run the migrations."""
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()