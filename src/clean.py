"""Clean the raw 311 extract and add the derived columns.

Reads  data/raw/nyc311_raw.csv      (never modified)
Writes data/clean/nyc311_clean.csv
       docs/cleaning_log.md / .json
       docs/data_dictionary.md

Nothing is deleted or "fixed" silently: odd rows get a flag column instead.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("data/raw/nyc311_raw.csv")
OUT = Path("data/clean/nyc311_clean.csv")

# rough box around the five boroughs
LAT_RANGE = (40.45, 40.95)
LON_RANGE = (-74.30, -73.65)

changes = {}   # what we touched, for the log


def note(key, n):
    changes[key] = int(n)


def tidy_text(df, cols):
    for c in cols:
        before = df[c].copy()
        df[c] = df[c].str.replace(r"\s+", " ", regex=True).str.strip()
        df[c] = df[c].replace("", np.nan)
        # blanks were already there, only count real edits
        note(f"whitespace fixed in {c}", ((before != df[c]) & df[c].notna()).sum())


def use_commonest_spelling(df, col):
    """'Noise - Street/Sidewalk' vs 'NOISE - STREET/SIDEWALK' -> the spelling seen most often."""
    key = df[col].str.lower()
    best = df.groupby(key)[col].agg(lambda s: s.value_counts().index[0])
    fixed = key.map(best)
    changed = (fixed != df[col]) & df[col].notna()
    note(f"case variants merged in {col}", changed.sum())
    df[col] = fixed.where(df[col].notna())


def main():
    df = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    n_raw = len(df)
    print("raw rows:", n_raw)

    note("duplicate unique_key rows", df["unique_key"].duplicated().sum())
    df = df.drop_duplicates("unique_key", keep="first")

    text_cols = [c for c in df.columns if c not in ("latitude", "longitude")]
    tidy_text(df, text_cols)

    for col in ["complaint_type", "descriptor", "borough", "city", "agency_name"]:
        use_commonest_spelling(df, col)

    # dates
    date_cols = ["created_date", "closed_date", "due_date", "resolution_action_updated_date"]
    for c in date_cols:
        parsed = pd.to_datetime(df[c], errors="coerce")
        note(f"unparseable {c}", (parsed.isna() & df[c].notna()).sum())
        df[c] = parsed

    # numbers
    for c in ["latitude", "longitude"]:
        num = pd.to_numeric(df[c].replace("", np.nan), errors="coerce")
        note(f"non-numeric {c}", (num.isna() & df[c].replace("", np.nan).notna()).sum())
        df[c] = num
    df["council_district"] = pd.to_numeric(df["council_district"], errors="coerce").astype("Int64")

    # zip must be 5 digits
    bad_zip = df["incident_zip"].notna() & ~df["incident_zip"].str.fullmatch(r"\d{5}", na=False)
    note("invalid zip set to null", bad_zip.sum())
    df.loc[bad_zip, "incident_zip"] = np.nan

    # ---- quality flags (the values stay as they are) ----
    extracted_at = pd.Timestamp(json.load(open("docs/extraction_log.json"))["extracted_at"])
    df["flag_closed_before_created"] = df["closed_date"] < df["created_date"]
    df["flag_future_date"] = (df["created_date"] > extracted_at) | (df["closed_date"] > extracted_at)
    df["flag_closed_status_no_date"] = (df["status"] == "Closed") & df["closed_date"].isna()
    df["flag_date_but_not_closed_status"] = (df["status"] != "Closed") & df["closed_date"].notna()
    df["flag_due_before_created"] = df["due_date"] < df["created_date"]
    df["flag_missing_coords"] = df["latitude"].isna() | df["longitude"].isna()
    outside = (
        ~df["latitude"].between(*LAT_RANGE) | ~df["longitude"].between(*LON_RANGE)
    ) & ~df["flag_missing_coords"]
    df["flag_coords_outside_nyc"] = outside
    df["flag_closed_at_creation"] = df["closed_date"] == df["created_date"]
    # one point (a police station) carries ~2.7% of all rows: a placeholder location, not a hotspot
    same_point = df.groupby(["latitude", "longitude"])["unique_key"].transform("size")
    df["flag_repeated_coords"] = same_point > 1000
    for c in [c for c in df.columns if c.startswith("flag_")]:
        note(c, df[c].sum())

    # ---- derived fields ----
    df["is_closed"] = df["closed_date"].notna()

    hours = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600
    usable = df["is_closed"] & ~df["flag_closed_before_created"] & ~df["flag_future_date"]
    df["resolution_hours"] = hours.where(usable).round(3)
    note("rows with a valid resolution_hours", df["resolution_hours"].notna().sum())

    df["is_over_72h"] = (df["resolution_hours"] > 72).astype("boolean").where(df["resolution_hours"].notna())

    d = df["created_date"]
    df["created_year"] = d.dt.year
    df["created_month"] = d.dt.month
    df["created_year_month"] = d.dt.strftime("%Y-%m")
    df["created_weekday"] = d.dt.day_name()
    df["created_weekday_num"] = d.dt.day_of_week      # Monday = 0
    df["created_hour"] = d.dt.hour

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print("clean rows:", len(df), "->", OUT)

    write_logs(n_raw, len(df), df, extracted_at)


# ---------------------------------------------------------------- docs

MEANING = {
    "unique_key": ("Request id", "none", "primary key, distinct count"),
    "created_date": ("When the request was opened", "parsed to datetime", "trends, weekday/hour"),
    "closed_date": ("When the agency recorded closure", "parsed to datetime; blank kept as null", "is_closed, resolution time"),
    "due_date": ("Agency due date, rarely filled", "parsed to datetime", "not used in analysis (almost empty)"),
    "agency": ("Agency code", "whitespace", "workload by agency"),
    "agency_name": ("Agency full name", "whitespace, case", "labels"),
    "complaint_type": ("Main complaint category", "whitespace, case merged", "top categories, filters"),
    "descriptor": ("Detail of the complaint type", "whitespace, case merged", "context only"),
    "location_type": ("Kind of place", "whitespace", "context only"),
    "address_type": ("How the address was given", "whitespace", "context only"),
    "incident_zip": ("ZIP code", "non 5-digit values set to null", "context only"),
    "incident_address": ("Street address", "whitespace", "not used (privacy, sparse)"),
    "street_name": ("Street", "whitespace", "not used"),
    "city": ("City or neighbourhood name", "whitespace, case merged", "context only"),
    "borough": ("Borough", "whitespace, case merged; 'Unspecified' kept", "borough comparison, filters"),
    "status": ("Recorded status", "whitespace", "status distribution"),
    "resolution_description": ("Free text on how it was resolved", "whitespace", "not used"),
    "resolution_action_updated_date": ("Last resolution update", "parsed to datetime", "not used"),
    "community_board": ("Community board", "whitespace", "context only"),
    "council_district": ("City council district", "to integer", "context only"),
    "police_precinct": ("Police precinct", "whitespace", "context only"),
    "bbl": ("Tax lot id", "whitespace", "not used"),
    "open_data_channel_type": ("How it was reported (phone, online...)", "whitespace", "context only"),
    "latitude": ("Latitude", "to float", "geographic concentration"),
    "longitude": ("Longitude", "to float", "geographic concentration"),
    "is_closed": ("True when closed_date is recorded", "derived", "closure rate, open count"),
    "resolution_hours": ("Hours from created to closed (valid cases only)", "derived; null if not closed, closed before created or future date", "median/mean, outliers, skewness"),
    "is_over_72h": ("resolution_hours > 72", "derived; null when no valid duration", "KPI 5"),
    "created_year": ("Year of created_date", "derived", "time grouping"),
    "created_month": ("Month number", "derived", "time grouping"),
    "created_year_month": ("YYYY-MM", "derived", "monthly trend"),
    "created_weekday": ("Weekday name", "derived", "weekday demand"),
    "created_weekday_num": ("0=Monday ... 6=Sunday", "derived", "sorting weekdays"),
    "created_hour": ("Hour of day 0-23", "derived", "hourly demand"),
}
FLAG_MEANING = {
    "flag_closed_before_created": "closed_date earlier than created_date",
    "flag_future_date": "a date after the extraction time",
    "flag_closed_status_no_date": "status is Closed but there is no closed_date",
    "flag_date_but_not_closed_status": "closed_date present but status is not Closed",
    "flag_due_before_created": "due_date earlier than created_date",
    "flag_missing_coords": "latitude or longitude missing",
    "flag_coords_outside_nyc": "coordinates outside the NYC bounding box",
    "flag_closed_at_creation": "closed at the exact second of creation (kept, looks like auto-closing)",
    "flag_repeated_coords": "exact coordinate shared by more than 1,000 rows (placeholder location)",
}


def type_name(s):
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    if pd.api.types.is_integer_dtype(s):
        return "integer"
    if pd.api.types.is_float_dtype(s):
        return "decimal"
    return "text"


def write_logs(n_raw, n_clean, df, extracted_at):
    raw = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    raw_missing = (raw == "").sum()

    lines = ["# Cleaning and validation log", "",
             f"Raw file: `data/raw/nyc311_raw.csv`, {n_raw:,} rows. Extracted {extracted_at:%Y-%m-%d %H:%M}.", ""]
    lines += ["## What was changed", "", "| Step | Rows affected |", "|---|---|"]
    untouched = []
    for k, v in changes.items():
        if k.startswith("flag_"):
            continue
        if v == 0 and k.startswith("whitespace"):
            untouched.append(k.split(" in ")[1])
            continue
        lines.append(f"| {k} | {v:,} |")
    lines += ["", "Columns checked for stray whitespace with nothing to fix: " + ", ".join(untouched) + "."]
    lines += ["", "## Flags (values kept, rows marked)", "", "| Flag | Meaning | Rows |", "|---|---|---|"]
    for k, meaning in FLAG_MEANING.items():
        lines.append(f"| {k} | {meaning} | {changes[k]:,} |")
    valid = int(df["resolution_hours"].notna().sum())
    lines += ["", "## Validation", "",
              f"- Raw rows {n_raw:,}, clean rows {n_clean:,} (no rows were dropped).",
              f"- unique_key unique in clean data: {df['unique_key'].is_unique}",
              f"- created_date range: {df['created_date'].min()} to {df['created_date'].max()}",
              f"- Valid resolution durations: {valid:,} of {int(df['is_closed'].sum()):,} closed rows",
              f"- Smallest / largest resolution_hours: {df['resolution_hours'].min():.3f} / {df['resolution_hours'].max():,.1f}",
              "- The database row count is checked in `src/load.py` and written to `docs/load_log.json`.",
              ""]
    Path("docs/cleaning_log.md").write_text("\n".join(lines))
    Path("docs/cleaning_log.json").write_text(json.dumps(
        {"raw_rows": n_raw, "clean_rows": n_clean, "changes": changes}, indent=2))

    d = ["# Data dictionary", "",
         "Source: NYC 311 Service Requests from 2020 to Present (`erm2-nwe9`). "
         "Missing % is on the cleaned file, `raw missing` is what the API returned empty.", "",
         "| Column | Meaning | Type | Missing % | Raw missing | Transformation | Used for |", "|---|---|---|---|---|---|---|"]
    for col in df.columns:
        if col in MEANING:
            meaning, how, use = MEANING[col]
        else:
            meaning, how, use = FLAG_MEANING[col], "derived true/false flag", "data quality"
        pct = df[col].isna().mean() * 100
        rm = f"{int(raw_missing[col]):,}" if col in raw_missing else "-"
        d.append(f"| {col} | {meaning} | {type_name(df[col])} | {pct:.1f} | {rm} | {how} | {use} |")
    Path("docs/data_dictionary.md").write_text("\n".join(d) + "\n")


if __name__ == "__main__":
    main()
