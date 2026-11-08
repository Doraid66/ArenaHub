"""GET /fields"""

from app.catalog.demo_data import (
    DEMO_FACILITY_ID,
    FULL_SOCCER_FIELD_ID,
    SUB_FIELD_A_ID,
    SUB_FIELD_B_ID,
    SUB_FIELD_C_ID,
)


def test_requires_login(anon_client):
    r = anon_client.get("/fields")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_lists_all_seeded_fields_with_the_agreed_shape(client):
    r = client.get("/fields")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 7
    for item in items:
        assert set(item) == {"id", "facility_id", "parent_field_id", "name", "sport"}


def test_sub_fields_point_to_the_full_field_in_the_same_facility(client):
    items = {item["id"]: item for item in client.get("/fields").json()["items"]}
    for sub_id in (SUB_FIELD_A_ID, SUB_FIELD_B_ID, SUB_FIELD_C_ID):
        sub = items[str(sub_id)]
        assert sub["parent_field_id"] == str(FULL_SOCCER_FIELD_ID)
        assert sub["facility_id"] == str(DEMO_FACILITY_ID)
    assert items[str(FULL_SOCCER_FIELD_ID)]["parent_field_id"] is None


def test_full_fields_are_listed_before_their_sub_fields(client):
    ids = [item["id"] for item in client.get("/fields").json()["items"]]
    assert ids.index(str(FULL_SOCCER_FIELD_ID)) < ids.index(str(SUB_FIELD_A_ID))