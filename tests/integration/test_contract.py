"""Contract conformance.

1. Drift: the committed contracts/openapi.json must match what the app generates.
2. Schemathesis: generate valid and invalid requests from the contract, send them to the
   app, and check every response matches the contract (no 500s, documented status codes,
   content types and body shapes, and protected routes really require a valid login).
"""

import uuid  # Currently unused; left in place.

import pytest  # Fixtures.
import schemathesis  # Generates requests from the OpenAPI contract.
from fastapi import Security  # Declare the bearer-token dependency.
from fastapi.security import HTTPAuthorizationCredentials  # The parsed bearer token.
from schemathesis.checks import positive_data_acceptance  # A check we skip for some routes.

from app.auth.demo_accounts import DEMO_PLAYER_1_ID  # The stand-in logged-in user.
from app.catalog.routes import get_availability_checker  # Dependency replaced by a fake.
from app.core.errors import UnauthenticatedError  # The shared 401 error.
from app.core.principal import Principal, bearer_scheme, get_current_principal  # Login pieces to stand in for.
from app.main import app  # The application under test.
from scripts.export_openapi import CONTRACT_PATH, render_contract  # The saved and the live contract.
from tests.conftest import FakeAvailability  # Fake engine.


def test_committed_contract_is_up_to_date():  # Guards against forgetting to re-export.
    saved = CONTRACT_PATH.read_text(encoding="utf-8") if CONTRACT_PATH.exists() else ""  # The committed file, or empty.
    assert saved == render_contract(), (  # Must match what the app generates now.
        "contracts/openapi.json is out of date. Run: python -m scripts.export_openapi"  # How to fix it.
    )  # Finish the assertion.


# The contract is loaded from the app itself; the drift test above guarantees it is
# identical to the committed file.
schema = schemathesis.openapi.from_asgi("/openapi.json", app)  # Load the contract straight from the running app.

TEST_TOKEN = "contract-test-token"  # The only token the stand-in login accepts.

# Operations with a rule OpenAPI can't express ("end" must be after "start"). A request
# can match the contract and still be rejected with 422, so Schemathesis must not treat
# that as a bug. Add Person 1's and Person 2's routes here when they are registered:
#   "POST /fields/{field_id}/bookings", "POST /fields/{field_id}/blocks"
CROSS_FIELD_RULES = {  # Routes where a valid-looking request may still get a 422.
    "POST /fields/{field_id}/bookings",  # The service also checks interval ordering and future starts.
    "GET /fields/{field_id}/availability",  # End must be after start.
    "POST /fields/{field_id}/blocks",  # End must be after start.
}  # Finish the set.


def stand_in_principal(  # Replacement for the real login check.
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),  # The bearer token, if sent.
) -> Principal:  # The caller.
    """Behaves like a real login check: only the test token is valid, anything else is 401.

    (An "always logged in" stand-in would hide missing or invalid authentication.)
    """
    if credentials is None or credentials.credentials != TEST_TOKEN:  # Missing or wrong token.
        raise UnauthenticatedError()  # Return a 401.
    return Principal(user_id=DEMO_PLAYER_1_ID)  # The token is right; act as player 1.


@pytest.fixture(scope="module", autouse=True)  # Applies once to every test in this file.
def stand_ins_for_teammates():  # Install the stand-ins.
    """Stand-ins for teammates' parts, so generated requests reach the catalog logic."""
    app.dependency_overrides[get_current_principal] = stand_in_principal  # Use the stand-in login.
    app.dependency_overrides[get_availability_checker] = lambda: FakeAvailability()  # Use the fake engine.
    yield  # Run the tests.
    app.dependency_overrides.clear()  # Remove the stand-ins.


@schema.parametrize()  # One test per operation in the contract.
def test_api_conforms_to_contract(case):  # Generated requests must get contract-conforming answers.
    # Send the valid token so requests reach the endpoint logic. Schemathesis also sends
    # requests with no token and with a wrong one, and expects 401 for those.
    excluded = [positive_data_acceptance] if case.operation.label in CROSS_FIELD_RULES else []  # Skip one check where 422 is legitimate.
    case.call_and_validate(  # Send the request and check the response.
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},  # Valid token.
        excluded_checks=excluded,  # Checks to skip.
    )  # Finish the call.
