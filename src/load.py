import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from db import get_engine

CSV = Path("data/clean/nyc311_clean.csv")
SCHEMA = Path("sql/schema.sql")
BATCH = 1000


def make_database():
    name = os.getenv("DB_NAME", "urban_pulse_db")
    try:
        with get_engine().connect():
            return
    except OperationalError:
        pass

    engine = get_engine("postgres").execution_options(isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(text("select 1 from pg_database where datname = :n"), {"n": name}).scalar()
        if not exists:
            conn.execute(text(f'create database "{name}"'))


def read_clean():
    df = pd.read_csv(CSV, dtype={"incident_zip": str, "unique_key": "int64"}, low_memory=False)
    for col in ["created_date", "closed_date", "due_date", "resolution_action_updated_date"]:
        df[col] = pd.to_datetime(df[col])
    df["council_district"] = df["council_district"].astype("Int64")
    return df.astype(object).where(df.notna(), None)


def split_schema():
    sql = SCHEMA.read_text()
    create_statement = ""
    index_statements = []
    for part in sql.split(";"):
        statement = part.strip()
        if statement == "":
            continue
        if "CREATE TABLE" in statement:
            create_statement = statement
        if statement.startswith("CREATE INDEX"):
            index_statements.append(statement)
    return create_statement, index_statements


def create_staging_table(engine, create_sql):
    staging_sql = create_sql.replace("CREATE TABLE service_requests", "CREATE TABLE service_requests_staging")
    with engine.begin() as conn:
        conn.execute(text("drop table if exists service_requests_staging"))
        conn.execute(text(staging_sql))


def insert_batches(engine, df):
    total = len(df)
    for start in range(0, total, BATCH):
        batch = df.iloc[start:start + BATCH]
        batch.to_sql("service_requests_staging", engine, if_exists="append", index=False)


def same_number(db_value, csv_value):
    if db_value is None and csv_value is None:
        return True
    if db_value is None or csv_value is None:
        return False
    return abs(db_value - float(csv_value)) < 1e-6


def count_matching_sample_rows(engine, df):
    sample = df.sample(5, random_state=1)
    sample_ok = 0
    sql = text("select agency, complaint_type, borough, resolution_hours "
               "from service_requests_staging where unique_key = :k")
    with engine.connect() as conn:
        for _, csv_row in sample.iterrows():
            db_row = conn.execute(sql, {"k": int(csv_row["unique_key"])}).fetchone()
            same = True
            if db_row[0] != csv_row["agency"]:
                same = False
            if db_row[1] != csv_row["complaint_type"]:
                same = False
            if db_row[2] != csv_row["borough"]:
                same = False
            if not same_number(db_row[3], csv_row["resolution_hours"]):
                same = False
            if same:
                sample_ok += 1
    return sample_ok, len(sample)


def validate_staging(engine, df):
    n_csv = len(df)
    numbers = {}
    with engine.connect() as conn:
        numbers["n_stage"] = conn.execute(text("select count(*) from service_requests_staging")).scalar()
        numbers["n_distinct"] = conn.execute(text("select count(distinct unique_key) from service_requests_staging")).scalar()
        dates = conn.execute(text("select min(created_date), max(created_date) from service_requests_staging")).fetchone()
        numbers["first_date"] = dates[0]
        numbers["last_date"] = dates[1]
        numbers["n_hours"] = conn.execute(text("select count(*) from service_requests_staging where resolution_hours is not null")).scalar()
        negative = conn.execute(text("select count(*) from service_requests_staging where resolution_hours < 0")).scalar()

    problems = []
    if numbers["n_stage"] != n_csv:
        problems.append(f"row count: csv {n_csv} vs staging {numbers['n_stage']}")
    if numbers["n_distinct"] != numbers["n_stage"]:
        problems.append("duplicate keys in staging")
    if numbers["n_hours"] != int(df["resolution_hours"].notna().sum()):
        problems.append("resolution_hours count differs from csv")
    if negative:
        problems.append(f"{negative} negative resolution_hours")

    sample_ok, sample_size = count_matching_sample_rows(engine, df)
    numbers["sample_ok"] = sample_ok
    if sample_ok != sample_size:
        problems.append(f"only {sample_ok}/{sample_size} sampled rows match the csv")
    return problems, numbers


def publish_staging(engine, index_sql):
    with engine.begin() as conn:
        conn.execute(text("drop table if exists service_requests"))
        conn.execute(text("alter table service_requests_staging rename to service_requests"))
        conn.execute(text("alter index service_requests_staging_pkey rename to service_requests_pkey"))
        for statement in index_sql:
            conn.execute(text(statement))


def main():
    make_database()
    engine = get_engine()
    df = read_clean()
    n_csv = len(df)
    if not df["unique_key"].is_unique:
        raise SystemExit("duplicate unique_key in the clean file, fix that first")

    create_sql, index_sql = split_schema()
    create_staging_table(engine, create_sql)

    insert_batches(engine, df)

    problems, numbers = validate_staging(engine, df)
    if len(problems) > 0:
        raise SystemExit("validation failed, old table untouched: " + "; ".join(problems))

    publish_staging(engine, index_sql)

    with engine.connect() as conn:
        n_final = conn.execute(text("select count(*) from service_requests")).scalar()

    log = {
        "loaded_at": datetime.now().isoformat(timespec="seconds"),
        "clean_csv_rows": n_csv,
        "staging_rows": int(numbers["n_stage"]),
        "final_rows": int(n_final),
        "distinct_unique_keys": int(numbers["n_distinct"]),
        "created_date_range": [str(numbers["first_date"]), str(numbers["last_date"])],
        "rows_with_resolution_hours": int(numbers["n_hours"]),
        "sample_rows_matching_csv": f"{numbers['sample_ok']}/5",
    }
    Path("docs/load_log.json").write_text(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
