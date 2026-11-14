"""Load the cleaned CSV into PostgreSQL through a staging table.

Steps: make the database if needed -> create service_requests_staging ->
insert in batches (retry on a failed batch) -> validate -> swap the staging
table in as service_requests inside one transaction.
If validation fails, the old service_requests table is left alone.

Run:  python src/load.py
"""
import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from psycopg2.extras import execute_values
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from db import get_engine

CSV = Path("data/clean/nyc311_clean.csv")
SCHEMA = Path("sql/schema.sql")
BATCH = 5000
TRIES = 3


def make_database():
    import os
    name = os.getenv("DB_NAME", "urban_pulse_db")
    eng = get_engine("postgres").execution_options(isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        exists = conn.execute(text("select 1 from pg_database where datname = :n"), {"n": name}).scalar()
        if not exists:
            conn.execute(text(f'create database "{name}"'))
            print("created database", name)


def read_clean():
    df = pd.read_csv(CSV, dtype={"incident_zip": str, "unique_key": "int64"}, low_memory=False)
    for c in ["created_date", "closed_date", "due_date", "resolution_action_updated_date"]:
        df[c] = pd.to_datetime(df[c])
    df["council_district"] = df["council_district"].astype("Int64")
    # python None instead of NaN/NaT/NA so psycopg2 sends proper NULLs
    return df.astype(object).where(df.notna(), None)


def split_schema():
    sql = SCHEMA.read_text()
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    create = [s for s in statements if "CREATE TABLE" in s][0]
    indexes = [s for s in statements if s.startswith("CREATE INDEX")]
    return create, indexes


def insert_batches(engine, df):
    cols = list(df.columns)
    query = (f"insert into service_requests_staging ({', '.join(cols)}) values %s "
             "on conflict (unique_key) do nothing")
    rows = list(df.itertuples(index=False, name=None))
    for start in range(0, len(rows), BATCH):
        chunk = rows[start:start + BATCH]
        for attempt in range(1, TRIES + 1):
            try:
                raw = engine.raw_connection()
                try:
                    with raw.cursor() as cur:
                        execute_values(cur, query, chunk, page_size=1000)
                    raw.commit()
                finally:
                    raw.close()
                break
            except Exception as e:
                print(f"  batch at {start} failed ({type(e).__name__}), try {attempt}")
                if attempt == TRIES:
                    raise
                time.sleep(2 * attempt)
        if (start // BATCH) % 5 == 0:
            print(f"  loaded {min(start + BATCH, len(rows)):,} / {len(rows):,}")


def main():
    make_database()
    engine = get_engine()
    df = read_clean()
    n_csv = len(df)
    if not df["unique_key"].is_unique:
        raise SystemExit("duplicate unique_key in the clean file, fix that first")

    create_sql, index_sql = split_schema()
    staging_sql = create_sql.replace("CREATE TABLE service_requests", "CREATE TABLE service_requests_staging")

    with engine.begin() as conn:
        conn.execute(text("drop table if exists service_requests_staging"))
        conn.execute(text(staging_sql))

    print("loading", n_csv, "rows into staging")
    insert_batches(engine, df)

    # ---- validation on the staging table ----
    with engine.connect() as conn:
        n_stage = conn.execute(text("select count(*) from service_requests_staging")).scalar()
        n_distinct = conn.execute(text("select count(distinct unique_key) from service_requests_staging")).scalar()
        lo, hi = conn.execute(text("select min(created_date), max(created_date) from service_requests_staging")).one()
        n_hours = conn.execute(text("select count(*) from service_requests_staging where resolution_hours is not null")).scalar()
        neg = conn.execute(text("select count(*) from service_requests_staging where resolution_hours < 0")).scalar()
    problems = []
    if n_stage != n_csv:
        problems.append(f"row count: csv {n_csv} vs staging {n_stage}")
    if n_distinct != n_stage:
        problems.append("duplicate keys in staging")
    if n_hours != int(df["resolution_hours"].notna().sum()):
        problems.append("resolution_hours count differs from csv")
    if neg:
        problems.append(f"{neg} negative resolution_hours")

    # compare a few random rows with the csv
    sample = df.sample(5, random_state=1)
    sample_ok = 0
    with engine.connect() as conn:
        for _, r in sample.iterrows():
            row = conn.execute(
                text("select agency, complaint_type, borough, resolution_hours from service_requests_staging where unique_key = :k"),
                {"k": int(r["unique_key"])}).one()
            same = (row[0] == r["agency"] and row[1] == r["complaint_type"] and row[2] == r["borough"]
                    and (row[3] is None and r["resolution_hours"] is None
                         or row[3] is not None and r["resolution_hours"] is not None
                         and abs(row[3] - float(r["resolution_hours"])) < 1e-6))
            sample_ok += bool(same)
    if sample_ok != len(sample):
        problems.append(f"only {sample_ok}/5 sampled rows match the csv")

    if problems:
        print("validation failed, old table untouched:")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)

    # ---- publish ----
    with engine.begin() as conn:
        conn.execute(text("drop table if exists service_requests"))
        conn.execute(text("alter table service_requests_staging rename to service_requests"))
        conn.execute(text("alter index service_requests_staging_pkey rename to service_requests_pkey"))
        for stmt in index_sql:
            conn.execute(text(stmt))

    with engine.connect() as conn:
        n_final = conn.execute(text("select count(*) from service_requests")).scalar()

    log = {
        "loaded_at": datetime.now().isoformat(timespec="seconds"),
        "clean_csv_rows": n_csv,
        "staging_rows": int(n_stage),
        "final_rows": int(n_final),
        "distinct_unique_keys": int(n_distinct),
        "created_date_range": [str(lo), str(hi)],
        "rows_with_resolution_hours": int(n_hours),
        "sample_rows_matching_csv": f"{sample_ok}/5",
    }
    Path("docs/load_log.json").write_text(json.dumps(log, indent=2))
    print("published service_requests:", n_final, "rows")
    print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
