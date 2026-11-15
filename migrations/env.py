"""Alembic environment: connects migrations to our settings and our shared Base."""

import importlib  # Import model modules by name.
from logging.config import fileConfig  # Load logging settings from alembic.ini.

from alembic import context  # Alembic's runtime context.
from sqlalchemy import create_engine, pool  # Build a connection and choose a pool type.

from app.core.config import get_settings  # Database URL comes from settings.
from app.core.database import Base  # The shared model base class.

config = context.config  # The loaded alembic.ini settings.

# Use the logging setup from alembic.ini when running the alembic command.
if config.config_file_name is not None:  # Only when run through the alembic command.
    fileConfig(config.config_file_name)  # Apply its logging settings.

# Import every module that defines models, so Base.metadata knows all tables.
# Modules that don't exist yet on this branch are skipped.
MODEL_MODULES = [  # Every module that defines tables.
    "app.catalog.models",       # Person 3: facilities, fields
    "app.auth.models",          # Person 2: users, manager_facilities
    "app.reservations.models",  # Person 1: reservations, idempotency_records
]  # Finish the module list.
for module_name in MODEL_MODULES:  # Import each one.
    try:  # The module may not exist on this branch.
        importlib.import_module(module_name)  # Importing registers its tables on Base.
    except ModuleNotFoundError as exc:  # The import failed.
        # Skip only if THIS module (or its package) is missing. Any other missing
        # import means the module exists but is broken, so show the real error.
        if not (module_name == exc.name or module_name.startswith(f"{exc.name}.")):  # Something else was missing.
            raise  # Show the real error.

target_metadata = Base.metadata  # The table definitions Alembic compares against.


def run_migrations_offline() -> None:  # Generate SQL without connecting.
    """Print the SQL instead of running it (alembic upgrade head --sql)."""
    context.configure(  # Set up Alembic for offline mode.
        url=get_settings().database_url,  # Only used to pick the SQL dialect.
        target_metadata=target_metadata,  # Our tables.
        literal_binds=True,  # Write values directly into the SQL text.
        dialect_opts={"paramstyle": "named"},  # Use named placeholders.
    )  # Finish the configuration.
    with context.begin_transaction():  # Wrap the output in a transaction.
        context.run_migrations()  # Emit the SQL.


def run_migrations_online() -> None:  # Connect and run the migrations for real.
    """Connect to the database and run the migrations."""
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)  # No pooling; this is a short-lived command.
    with engine.connect() as connection:  # Open one connection.
        context.configure(connection=connection, target_metadata=target_metadata)  # Set up Alembic for online mode.
        with context.begin_transaction():  # Run everything in one transaction.
            context.run_migrations()  # Apply the migrations.


if context.is_offline_mode():  # Was --sql requested?
    run_migrations_offline()  # Print the SQL.
else:  # Normal run.
    run_migrations_online()  # Change the database.
