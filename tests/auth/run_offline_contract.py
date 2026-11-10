"""Run existing API conformance tests against test-only SQLite, without Docker.

    python -m tests.auth.run_offline_contract

This verifies HTTP shapes, not PostgreSQL migrations or reservation concurrency.
The normal `python -m pytest` still runs against real PostgreSQL.
"""

import pytest

from app.core.database import get_db
from app.main import app
from tests.auth import offline_fixtures


class OfflineContractDatabase:
    @pytest.fixture(autouse=True)
    def wire_database(self, isolated_db):
        def database_override():
            yield isolated_db

        app.dependency_overrides[get_db] = database_override
        try:
            yield
        finally:
            app.dependency_overrides.pop(get_db, None)


def main() -> int:
    # Exclude the global fixture that recreates PostgreSQL; retain the existing
    # contract tests and their explicit stand-ins for authentication/availability.
    return pytest.main(
        ["--confcutdir=tests/integration", "tests/integration/test_contract.py", "-q"],
        plugins=[offline_fixtures, OfflineContractDatabase()],
    )


if __name__ == "__main__":
    raise SystemExit(main())
