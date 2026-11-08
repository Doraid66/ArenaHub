"""Application settings, read from environment variables (or a local .env file)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Where to read values from. "extra='ignore'" means unknown variables in .env
    # (like POSTGRES_PASSWORD, used only by Docker) don't cause an error.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # General
    app_name: str = "ArenaHub"
    environment: str = "development"
    log_level: str = "INFO"

    # Database: required, no default. Example:
    # postgresql+psycopg://arenahub:arenahub@localhost:5432/arenahub
    database_url: str

    # Login tokens (used by Person 2). The secret is required and must be long.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Booking holds (used by Person 1)
    hold_minutes: int = 10

    # Passwords for the seeded demo accounts (used by Person 2). Local test values only.
    seed_player_password: str | None = None
    seed_manager_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the settings, created once and then reused."""
    return Settings()