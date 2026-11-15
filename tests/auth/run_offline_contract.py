"""Run existing API conformance tests against test-only SQLite, without Docker.

    python -m tests.auth.run_offline_contract

This verifies HTTP shapes, not PostgreSQL migrations or reservation concurrency.
The normal `python -m pytest` still runs against real PostgreSQL.
"""

import pytest  # Run the tests programmatically.

from app.core.database import get_db  # The session dependency to replace.
from app.main import app  # The application under test.
from tests.auth import offline_fixtures  # SQLite fixtures used as a plugin.


class OfflineContractDatabase:  # Pytest plugin that wires the SQLite database in.
    @pytest.fixture(autouse=True)  # Applies to every test automatically.
    def wire_database(self, isolated_db):  # Point the app at the SQLite session.
        def database_override():  # Replacement for get_db.
            yield isolated_db  # Every request uses the test session.

        app.dependency_overrides[get_db] = database_override  # Install the override.
        try:  # Always remove it afterwards.
            yield  # Run the test.
        finally:  # Runs even if the test fails.
            app.dependency_overrides.pop(get_db, None)  # Remove only our override.


def main() -> int:  # Entry point; returns an exit code.
    # Exclude the global fixture that recreates PostgreSQL; retain the existing
    # contract tests and their explicit stand-ins for authentication/availability.
    return pytest.main(  # Run pytest and return its exit code.
        ["--confcutdir=tests/integration", "tests/integration/test_contract.py", "-q"],  # Skip the PostgreSQL conftest; run only the contract tests.
        plugins=[offline_fixtures, OfflineContractDatabase()],  # Add the SQLite fixtures and the wiring.
    )  # Finish the pytest call.


if __name__ == "__main__":  # Run only as a script.
    raise SystemExit(main())  # Use pytest's result as the exit code.
