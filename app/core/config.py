"""Application settings, read from environment variables (or a local .env file)."""

from functools import lru_cache  # Cache the settings object.

from pydantic import Field  # Add rules to a setting, like a minimum length.
from pydantic_settings import BaseSettings, SettingsConfigDict  # Settings loaded from the environment.


class Settings(BaseSettings):  # Every configurable value lives here.
    # Where to read values from. "extra='ignore'" means unknown variables in .env
    # (like POSTGRES_PASSWORD, used only by Docker) don't cause an error.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")  # Read .env; ignore unknown keys.

    app_name: str = "ArenaHub"  # Name shown in logs and docs.
    environment: str = "development"  # Which environment is running.
    log_level: str = "INFO"  # How much to log.

    # Database: required, no default. Example:
    # postgresql+psycopg://arenahub:arenahub@localhost:5432/arenahub
    database_url: str  # Connection string; the app cannot start without it.

    jwt_secret: str = Field(min_length=32)  # Token signing key; required and must be long (Person 2).
    jwt_algorithm: str = "HS256"  # Token signing algorithm.
    access_token_expire_minutes: int = 30  # How long a login token lasts.

    hold_minutes: int = 10  # How long a booking hold lasts (Person 1).

    seed_player_password: str | None = None  # Password for the demo players; local test value only.
    seed_manager_password: str | None = None  # Password for the demo manager; local test value only.


@lru_cache  # Build the settings once, then reuse them.
def get_settings() -> Settings:  # Access the settings anywhere in the app.
    """Return the settings, created once and then reused."""
    return Settings()  # Reads the environment on the first call only.
