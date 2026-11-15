"""GET /fields"""

from app.catalog.demo_data import (  # Fixed demo IDs.
    DEMO_FACILITY_ID,  # The main demo facility.
    FULL_SOCCER_FIELD_ID,  # The parent field.
    SUB_FIELD_A_ID,  # First sub-field.
    SUB_FIELD_B_ID,  # Second sub-field.
    SUB_FIELD_C_ID,  # Third sub-field.
)  # Finish the demo imports.


def test_requires_login(anon_client):  # Logged-out callers are refused.
    r = anon_client.get("/fields")  # Call without a token.
    assert r.status_code == 401  # Refused.
    assert r.json()["error"]["code"] == "unauthenticated"  # Shared error code.
    assert r.headers["WWW-Authenticate"] == "Bearer"  # Tells the client to use a bearer token.


def test_lists_all_seeded_fields_with_the_agreed_shape(client):  # Seven fields with exact keys.
    r = client.get("/fields")  # Ask for the list.
    assert r.status_code == 200  # Success.
    items = r.json()["items"]  # The fields.
    assert len(items) == 7  # All seeded fields.
    for item in items:  # Check each one.
        assert set(item) == {"id", "facility_id", "parent_field_id", "name", "sport"}  # Exactly the agreed keys.


def test_sub_fields_point_to_the_full_field_in_the_same_facility(client):  # Parent links are correct.
    items = {item["id"]: item for item in client.get("/fields").json()["items"]}  # Index fields by ID.
    for sub_id in (SUB_FIELD_A_ID, SUB_FIELD_B_ID, SUB_FIELD_C_ID):  # Each sub-field.
        sub = items[str(sub_id)]  # Look it up.
        assert sub["parent_field_id"] == str(FULL_SOCCER_FIELD_ID)  # Its parent is the full field.
        assert sub["facility_id"] == str(DEMO_FACILITY_ID)  # Same facility.
    assert items[str(FULL_SOCCER_FIELD_ID)]["parent_field_id"] is None  # The full field has no parent.


def test_full_fields_are_listed_before_their_sub_fields(client):  # Sort order is friendly.
    ids = [item["id"] for item in client.get("/fields").json()["items"]]  # IDs in response order.
    assert ids.index(str(FULL_SOCCER_FIELD_ID)) < ids.index(str(SUB_FIELD_A_ID))  # Parent comes first.
