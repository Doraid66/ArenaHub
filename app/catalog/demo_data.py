"""Fixed demo facilities and fields.

The IDs never change, so teammates can use them in tests and in their own seed data:
    from app.catalog.demo_data import DEMO_FACILITY_ID, FULL_SOCCER_FIELD_ID, ...
"""

import uuid

# ---------- Facilities ----------
DEMO_FACILITY_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")
OTHER_FACILITY_ID = uuid.UUID("10000000-0000-4000-8000-000000000002")  # for "manager of another facility" tests

# ---------- Fields in the demo facility ----------
FULL_SOCCER_FIELD_ID = uuid.UUID("20000000-0000-4000-8000-000000000001")  # parent of the three 7v7 fields
SUB_FIELD_A_ID = uuid.UUID("20000000-0000-4000-8000-000000000002")
SUB_FIELD_B_ID = uuid.UUID("20000000-0000-4000-8000-000000000003")
SUB_FIELD_C_ID = uuid.UUID("20000000-0000-4000-8000-000000000004")
BASKETBALL_COURT_ID = uuid.UUID("20000000-0000-4000-8000-000000000005")  # standalone
FOOTBALL_FIELD_ID = uuid.UUID("20000000-0000-4000-8000-000000000006")    # standalone

# ---------- Field in the other facility ----------
OTHER_SOCCER_FIELD_ID = uuid.UUID("20000000-0000-4000-8000-000000000101")  # standalone

FACILITIES = [
    {"id": DEMO_FACILITY_ID, "name": "ArenaHub Demo Centre"},
    {"id": OTHER_FACILITY_ID, "name": "Riverside Sports Complex"},
]

# Full fields and standalone fields first, then sub-fields (a sub-field needs its parent to exist).
# Only one level: a sub-field's parent is always a field without a parent.
FIELDS = [
    {"id": FULL_SOCCER_FIELD_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": None,
     "name": "Soccer Field (11v11)", "sport": "soccer"},
    {"id": BASKETBALL_COURT_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": None,
     "name": "Basketball Court", "sport": "basketball"},
    {"id": FOOTBALL_FIELD_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": None,
     "name": "Football Field", "sport": "football"},
    {"id": OTHER_SOCCER_FIELD_ID, "facility_id": OTHER_FACILITY_ID, "parent_field_id": None,
     "name": "Soccer Field (7v7)", "sport": "soccer"},
    {"id": SUB_FIELD_A_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": FULL_SOCCER_FIELD_ID,
     "name": "Soccer Field - 7v7 A", "sport": "soccer"},
    {"id": SUB_FIELD_B_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": FULL_SOCCER_FIELD_ID,
     "name": "Soccer Field - 7v7 B", "sport": "soccer"},
    {"id": SUB_FIELD_C_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": FULL_SOCCER_FIELD_ID,
     "name": "Soccer Field - 7v7 C", "sport": "soccer"},
]