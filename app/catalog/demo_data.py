"""Fixed demo facilities and fields.

The IDs never change, so teammates can use them in tests and in their own seed data:
    from app.catalog.demo_data import DEMO_FACILITY_ID, FULL_SOCCER_FIELD_ID, ...
"""

import uuid  # Build fixed UUID values.

DEMO_FACILITY_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")  # The main demo facility.
OTHER_FACILITY_ID = uuid.UUID("10000000-0000-4000-8000-000000000002")  # A second facility, for "manager of another facility" tests.

FULL_SOCCER_FIELD_ID = uuid.UUID("20000000-0000-4000-8000-000000000001")  # Parent of the three 7v7 fields.
SUB_FIELD_A_ID = uuid.UUID("20000000-0000-4000-8000-000000000002")  # First 7v7 sub-field.
SUB_FIELD_B_ID = uuid.UUID("20000000-0000-4000-8000-000000000003")  # Second 7v7 sub-field.
SUB_FIELD_C_ID = uuid.UUID("20000000-0000-4000-8000-000000000004")  # Third 7v7 sub-field.
BASKETBALL_COURT_ID = uuid.UUID("20000000-0000-4000-8000-000000000005")  # Standalone court, no sub-fields.
FOOTBALL_FIELD_ID = uuid.UUID("20000000-0000-4000-8000-000000000006")  # Standalone field, no sub-fields.

OTHER_SOCCER_FIELD_ID = uuid.UUID("20000000-0000-4000-8000-000000000101")  # Standalone field in the other facility.

FACILITIES = [  # Rows inserted into the facilities table.
    {"id": DEMO_FACILITY_ID, "name": "ArenaHub Demo Centre"},  # Main demo facility.
    {"id": OTHER_FACILITY_ID, "name": "Riverside Sports Complex"},  # Second facility.
]  # Finish the facilities.

# Full fields and standalone fields first, then sub-fields (a sub-field needs its parent to exist).
# Only one level: a sub-field's parent is always a field without a parent.
FIELDS = [  # Rows inserted into the fields table.
    {"id": FULL_SOCCER_FIELD_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": None,  # Full field: no parent.
     "name": "Soccer Field (11v11)", "sport": "soccer"},  # Name and sport.
    {"id": BASKETBALL_COURT_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": None,  # Standalone court.
     "name": "Basketball Court", "sport": "basketball"},  # Name and sport.
    {"id": FOOTBALL_FIELD_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": None,  # Standalone field.
     "name": "Football Field", "sport": "football"},  # Name and sport.
    {"id": OTHER_SOCCER_FIELD_ID, "facility_id": OTHER_FACILITY_ID, "parent_field_id": None,  # Field in the other facility.
     "name": "Soccer Field (7v7)", "sport": "soccer"},  # Name and sport.
    {"id": SUB_FIELD_A_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": FULL_SOCCER_FIELD_ID,  # Sub-field of the full soccer field.
     "name": "Soccer Field - 7v7 A", "sport": "soccer"},  # Name and sport.
    {"id": SUB_FIELD_B_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": FULL_SOCCER_FIELD_ID,  # Sub-field of the full soccer field.
     "name": "Soccer Field - 7v7 B", "sport": "soccer"},  # Name and sport.
    {"id": SUB_FIELD_C_ID, "facility_id": DEMO_FACILITY_ID, "parent_field_id": FULL_SOCCER_FIELD_ID,  # Sub-field of the full soccer field.
     "name": "Soccer Field - 7v7 C", "sport": "soccer"},  # Name and sport.
]  # Finish the fields.
