# Cleaning and validation log

Raw file: `data/raw/nyc311_raw.csv`, 105,540 rows. Extracted 2026-11-14 16:36.

## What was changed

| Step | Rows affected |
|---|---|
| duplicate unique_key rows | 0 |
| whitespace fixed in descriptor | 24 |
| whitespace fixed in incident_address | 20,588 |
| whitespace fixed in street_name | 20,588 |
| whitespace fixed in resolution_description | 13,045 |
| case variants merged in complaint_type | 150 |
| case variants merged in descriptor | 5 |
| case variants merged in borough | 0 |
| case variants merged in city | 3 |
| case variants merged in agency_name | 0 |
| unparseable created_date | 0 |
| unparseable closed_date | 0 |
| unparseable due_date | 0 |
| unparseable resolution_action_updated_date | 0 |
| non-numeric latitude | 0 |
| non-numeric longitude | 0 |
| invalid zip set to null | 0 |
| rows with a valid resolution_hours | 104,115 |

Columns checked for stray whitespace with nothing to fix: unique_key, created_date, closed_date, due_date, agency, agency_name, complaint_type, location_type, address_type, incident_zip, city, borough, status, resolution_action_updated_date, community_board, council_district, police_precinct, bbl, open_data_channel_type.

## Flags (values kept, rows marked)

| Flag | Meaning | Rows |
|---|---|---|
| flag_closed_before_created | closed_date earlier than created_date | 38 |
| flag_future_date | a date after the extraction time | 0 |
| flag_closed_status_no_date | status is Closed but there is no closed_date | 352 |
| flag_date_but_not_closed_status | closed_date present but status is not Closed | 85 |
| flag_due_before_created | due_date earlier than created_date | 0 |
| flag_missing_coords | latitude or longitude missing | 1,648 |
| flag_coords_outside_nyc | coordinates outside the NYC bounding box | 0 |
| flag_closed_at_creation | closed at the exact second of creation (kept, looks like auto-closing) | 2,174 |
| flag_repeated_coords | exact coordinate shared by more than 1,000 rows (placeholder location) | 2,887 |

## Validation

- Raw rows 105,540, clean rows 105,540 (no rows were dropped).
- unique_key unique in clean data: True
- created_date range: 2025-01-01 00:00:19 to 2025-06-30 23:59:24
- Valid resolution durations: 104,115 of 104,153 closed rows
- Smallest / largest resolution_hours: 0.000 / 15,567.6
- The database row count is checked in `src/load.py` and written to `docs/load_log.json`.
