"""Contract conformance.

1. Drift: the committed contracts/openapi.json must match what the app generates.
2. Schemathesis: generate valid and invalid requests from the contract, send them to the
   app, and check every response matches the contract (no 500s, documented status codes,
   content types and body shapes, and protected routes really require a valid login).
"""

import uuid

import pytest
import schemathesis
from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials
from schemathesis.checks import positive_data_acceptance

from app.auth.demo_accounts import DEMO_PLAYER_1_ID
from app.catalog.routes import get_availability_checker
from app.core.errors import UnauthenticatedError
from app.core.principal import Principal, bearer_scheme, get_current_principal
from app.main import app
from scripts.export_openapi import CONTRACT_PATH, render_contract
from tests.conftest import FakeAvailability


def test_committed_contract_is_up_to_date():
    saved = CONTRACT_PATH.read_text(encoding="utf-8") if CONTRACT_PATH.exists() else ""
    assert saved == render_contract(), (
        "contracts/openapi.json is out of date. Run: python -m scripts.export_openapi"
    )


# The contract is loaded from the app itself; the drift test above guarantees it is
# identical to the committed file.
schema = schemathesis.openapi.from_asgi("/openapi.json", app)

TEST_TOKEN = "contract-test-token"

# Operations with a rule OpenAPI can't express ("end" must be after "start"). A request
# can match the contract and still be rejected with 422, so Schemathesis must not treat
# that as a bug. Add Person 1's and Person 2's routes here when they are registered:
#   "POST /fields/{field_id}/bookings", "POST /fields/{field_id}/blocks"
CROSS_FIELD_RULES = {
    "GET /fields/{field_id}/availability",
    "POST /fields/{field_id}/blocks",
}


def stand_in_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> Principal:
    """Behaves like a real login check: only the test token is valid, anything else is 401.

    (An "always logged in" stand-in would hide missing or invalid authentication.)
    """
    if credentials is None or credentials.credentials != TEST_TOKEN:
        raise UnauthenticatedError()
    return Principal(user_id=DEMO_PLAYER_1_ID)


@pytest.fixture(scope="module", autouse=True)
def stand_ins_for_teammates():
    """Stand-ins for teammates' parts, so generated requests reach the catalog logic."""
    app.dependency_overrides[get_current_principal] = stand_in_principal
    app.dependency_overrides[get_availability_checker] = lambda: FakeAvailability()
    yield
    app.dependency_overrides.clear()


@schema.parametrize()
def test_api_conforms_to_contract(case):
    # Send the valid token so requests reach the endpoint logic. Schemathesis also sends
    # requests with no token and with a wrong one, and expects 401 for those.
    excluded = [positive_data_acceptance] if case.operation.label in CROSS_FIELD_RULES else []
    case.call_and_validate(
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        excluded_checks=excluded,
    )
