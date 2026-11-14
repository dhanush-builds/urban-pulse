# Data dictionary

Source: NYC 311 Service Requests from 2020 to Present (`erm2-nwe9`). Missing % is on the cleaned file, `raw missing` is what the API returned empty.

| Column | Meaning | Type | Missing % | Raw missing | Transformation | Used for |
|---|---|---|---|---|---|---|
| unique_key | Request id | text | 0.0 | 0 | none | primary key, distinct count |
| created_date | When the request was opened | datetime | 0.0 | 0 | parsed to datetime | trends, weekday/hour |
| closed_date | When the agency recorded closure | datetime | 1.3 | 1,387 | parsed to datetime; blank kept as null | is_closed, resolution time |
| due_date | Agency due date, rarely filled | datetime | 99.6 | 105,067 | parsed to datetime | not used in analysis (almost empty) |
| agency | Agency code | text | 0.0 | 0 | whitespace | workload by agency |
| agency_name | Agency full name | text | 0.0 | 0 | whitespace, case | labels |
| complaint_type | Main complaint category | text | 0.0 | 0 | whitespace, case merged | top categories, filters |
| descriptor | Detail of the complaint type | text | 0.5 | 493 | whitespace, case merged | context only |
| location_type | Kind of place | text | 12.0 | 12,626 | whitespace | context only |
| address_type | How the address was given | text | 0.4 | 441 | whitespace | context only |
| incident_zip | ZIP code | text | 0.9 | 926 | non 5-digit values set to null | context only |
| incident_address | Street address | text | 3.7 | 3,892 | whitespace | not used (privacy, sparse) |
| street_name | Street | text | 3.7 | 3,895 | whitespace | not used |
| city | City or neighbourhood name | text | 4.2 | 4,463 | whitespace, case merged | context only |
| borough | Borough | text | 0.0 | 0 | whitespace, case merged; 'Unspecified' kept | borough comparison, filters |
| status | Recorded status | text | 0.0 | 0 | whitespace | status distribution |
| resolution_description | Free text on how it was resolved | text | 0.8 | 824 | whitespace | not used |
| resolution_action_updated_date | Last resolution update | datetime | 0.4 | 444 | parsed to datetime | not used |
| community_board | Community board | text | 0.0 | 0 | whitespace | context only |
| council_district | City council district | integer | 2.0 | 2,118 | to integer | context only |
| police_precinct | Police precinct | text | 0.0 | 0 | whitespace | context only |
| bbl | Tax lot id | text | 10.9 | 11,547 | whitespace | not used |
| open_data_channel_type | How it was reported (phone, online...) | text | 0.0 | 0 | whitespace | context only |
| latitude | Latitude | decimal | 1.6 | 1,648 | to float | geographic concentration |
| longitude | Longitude | decimal | 1.6 | 1,648 | to float | geographic concentration |
| flag_closed_before_created | closed_date earlier than created_date | boolean | 0.0 | - | derived true/false flag | data quality |
| flag_future_date | a date after the extraction time | boolean | 0.0 | - | derived true/false flag | data quality |
| flag_closed_status_no_date | status is Closed but there is no closed_date | boolean | 0.0 | - | derived true/false flag | data quality |
| flag_date_but_not_closed_status | closed_date present but status is not Closed | boolean | 0.0 | - | derived true/false flag | data quality |
| flag_due_before_created | due_date earlier than created_date | boolean | 0.0 | - | derived true/false flag | data quality |
| flag_missing_coords | latitude or longitude missing | boolean | 0.0 | - | derived true/false flag | data quality |
| flag_coords_outside_nyc | coordinates outside the NYC bounding box | boolean | 0.0 | - | derived true/false flag | data quality |
| flag_closed_at_creation | closed at the exact second of creation (kept, looks like auto-closing) | boolean | 0.0 | - | derived true/false flag | data quality |
| flag_repeated_coords | exact coordinate shared by more than 1,000 rows (placeholder location) | boolean | 0.0 | - | derived true/false flag | data quality |
| is_closed | True when closed_date is recorded | boolean | 0.0 | - | derived | closure rate, open count |
| resolution_hours | Hours from created to closed (valid cases only) | decimal | 1.4 | - | derived; null if not closed, closed before created or future date | median/mean, outliers, skewness |
| is_over_72h | resolution_hours > 72 | boolean | 1.4 | - | derived; null when no valid duration | KPI 5 |
| created_year | Year of created_date | integer | 0.0 | - | derived | time grouping |
| created_month | Month number | integer | 0.0 | - | derived | time grouping |
| created_year_month | YYYY-MM | text | 0.0 | - | derived | monthly trend |
| created_weekday | Weekday name | text | 0.0 | - | derived | weekday demand |
| created_weekday_num | 0=Monday ... 6=Sunday | integer | 0.0 | - | derived | sorting weekdays |
| created_hour | Hour of day 0-23 | integer | 0.0 | - | derived | hourly demand |
