-- Final table. src/load.py builds service_requests_staging from this same
-- definition, checks it, then swaps it in.

CREATE TABLE service_requests (
    unique_key                      BIGINT PRIMARY KEY,
    created_date                    TIMESTAMP NOT NULL,
    closed_date                     TIMESTAMP,
    due_date                        TIMESTAMP,
    agency                          VARCHAR(20),
    agency_name                     TEXT,
    complaint_type                  TEXT,
    descriptor                      TEXT,
    location_type                   TEXT,
    address_type                    TEXT,
    incident_zip                    VARCHAR(5),
    incident_address                TEXT,
    street_name                     TEXT,
    city                            TEXT,
    borough                         VARCHAR(30),
    status                          VARCHAR(30),
    resolution_description          TEXT,
    resolution_action_updated_date  TIMESTAMP,
    community_board                 TEXT,
    council_district                INTEGER,
    police_precinct                 TEXT,
    bbl                             TEXT,
    open_data_channel_type          TEXT,
    latitude                        DOUBLE PRECISION,
    longitude                       DOUBLE PRECISION,

    flag_closed_before_created      BOOLEAN,
    flag_future_date                BOOLEAN,
    flag_closed_status_no_date      BOOLEAN,
    flag_date_but_not_closed_status BOOLEAN,
    flag_due_before_created         BOOLEAN,
    flag_missing_coords             BOOLEAN,
    flag_coords_outside_nyc         BOOLEAN,
    flag_closed_at_creation         BOOLEAN,
    flag_repeated_coords            BOOLEAN,

    is_closed                       BOOLEAN,
    resolution_hours                DOUBLE PRECISION,
    is_over_72h                     BOOLEAN,
    created_year                    SMALLINT,
    created_month                   SMALLINT,
    created_year_month              CHAR(7),
    created_weekday                 VARCHAR(10),
    created_weekday_num             SMALLINT,
    created_hour                    SMALLINT
);

CREATE INDEX idx_sr_created   ON service_requests (created_date);
CREATE INDEX idx_sr_agency    ON service_requests (agency);
CREATE INDEX idx_sr_complaint ON service_requests (complaint_type);
CREATE INDEX idx_sr_borough   ON service_requests (borough);
CREATE INDEX idx_sr_ym        ON service_requests (created_year_month);
