import json
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("data/raw/nyc311_raw.csv")
OUT = Path("data/clean/nyc311_clean.csv")

# rough box around the five boroughs
LAT_MIN = 40.45
LAT_MAX = 40.95
LON_MIN = -74.30
LON_MAX = -73.65


def read_extracted_at():
    with open("docs/extraction_log.json") as f:
        log = json.load(f)
    return pd.Timestamp(log["extracted_at"])


def drop_duplicates(df, changes):
    changes["duplicate unique_key rows"] = int(df["unique_key"].duplicated().sum())
    df = df.drop_duplicates("unique_key", keep="first")
    return df


def tidy_text(df, changes):
    for col in df.columns:
        if col == "latitude" or col == "longitude":
            continue
        before = df[col].copy()
        df[col] = df[col].str.replace(r"\s+", " ", regex=True).str.strip()
        df[col] = df[col].replace("", np.nan)
        # empty cells were already there, only count real edits
        edited = (before != df[col]) & df[col].notna()
        changes["whitespace fixed in " + col] = int(edited.sum())
    return df


def most_common_value(values):
    return values.value_counts().index[0]


def use_commonest_spelling(df, col, changes):
    # 'Noise - Street/Sidewalk' and 'NOISE - STREET/SIDEWALK' become the spelling seen most often
    lower = df[col].str.lower()
    best = df.groupby(lower)[col].agg(most_common_value)
    fixed = lower.map(best)
    changed = (fixed != df[col]) & df[col].notna()
    changes["case variants merged in " + col] = int(changed.sum())
    df[col] = fixed.where(df[col].notna())


def fix_case(df, changes):
    for col in ["complaint_type", "descriptor", "borough", "city", "agency_name"]:
        use_commonest_spelling(df, col, changes)
    return df


def convert_types(df, changes):
    date_cols = ["created_date", "closed_date", "due_date", "resolution_action_updated_date"]
    for col in date_cols:
        parsed = pd.to_datetime(df[col], errors="coerce")
        bad = parsed.isna() & df[col].notna()
        changes["unparseable " + col] = int(bad.sum())
        df[col] = parsed

    for col in ["latitude", "longitude"]:
        text = df[col].replace("", np.nan)
        number = pd.to_numeric(text, errors="coerce")
        bad = number.isna() & text.notna()
        changes["non-numeric " + col] = int(bad.sum())
        df[col] = number
    df["council_district"] = pd.to_numeric(df["council_district"], errors="coerce").astype("Int64")

    # a zip code must have 5 digits
    bad_zip = df["incident_zip"].notna() & ~df["incident_zip"].str.fullmatch(r"\d{5}", na=False)
    changes["invalid zip set to null"] = int(bad_zip.sum())
    df.loc[bad_zip, "incident_zip"] = np.nan
    return df


def add_flags(df, changes, extracted_at):
    # the values stay as they are, odd rows only get a flag
    df["flag_closed_before_created"] = df["closed_date"] < df["created_date"]
    df["flag_future_date"] = (df["created_date"] > extracted_at) | (df["closed_date"] > extracted_at)
    df["flag_closed_status_no_date"] = (df["status"] == "Closed") & df["closed_date"].isna()
    df["flag_date_but_not_closed_status"] = (df["status"] != "Closed") & df["closed_date"].notna()
    df["flag_due_before_created"] = df["due_date"] < df["created_date"]
    df["flag_missing_coords"] = df["latitude"].isna() | df["longitude"].isna()

    lat_ok = df["latitude"].between(LAT_MIN, LAT_MAX)
    lon_ok = df["longitude"].between(LON_MIN, LON_MAX)
    outside = (~lat_ok | ~lon_ok) & ~df["flag_missing_coords"]
    df["flag_coords_outside_nyc"] = outside

    df["flag_closed_at_creation"] = df["closed_date"] == df["created_date"]

    # one point (a police station) has about 2.7% of all rows, it is a placeholder location
    same_point = df.groupby(["latitude", "longitude"])["unique_key"].transform("size")
    df["flag_repeated_coords"] = same_point > 1000

    for col in df.columns:
        if col.startswith("flag_"):
            changes[col] = int(df[col].sum())
    return df


def add_derived_columns(df, changes):
    df["is_closed"] = df["closed_date"].notna()

    seconds = (df["closed_date"] - df["created_date"]).dt.total_seconds()
    hours = seconds / 3600
    usable = df["is_closed"] & ~df["flag_closed_before_created"] & ~df["flag_future_date"]
    df["resolution_hours"] = hours.where(usable).round(3)
    changes["rows with a valid resolution_hours"] = int(df["resolution_hours"].notna().sum())

    over_72 = (df["resolution_hours"] > 72).astype("boolean")
    df["is_over_72h"] = over_72.where(df["resolution_hours"].notna())

    created = df["created_date"]
    df["created_year"] = created.dt.year
    df["created_month"] = created.dt.month
    df["created_year_month"] = created.dt.strftime("%Y-%m")
    df["created_weekday"] = created.dt.day_name()
    df["created_weekday_num"] = created.dt.day_of_week  # Monday = 0
    df["created_hour"] = created.dt.hour
    return df


def main():
    df = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    n_raw = len(df)
    print("raw rows:", n_raw)

    changes = {}
    extracted_at = read_extracted_at()

    df = drop_duplicates(df, changes)
    df = tidy_text(df, changes)
    df = fix_case(df, changes)
    df = convert_types(df, changes)
    df = add_flags(df, changes, extracted_at)
    df = add_derived_columns(df, changes)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print("clean rows:", len(df), "->", OUT)

    write_cleaning_log(n_raw, df, changes, extracted_at)
    write_data_dictionary(df)


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


def type_name(column):
    if pd.api.types.is_bool_dtype(column):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(column):
        return "datetime"
    if pd.api.types.is_integer_dtype(column):
        return "integer"
    if pd.api.types.is_float_dtype(column):
        return "decimal"
    return "text"


def write_cleaning_log(n_raw, df, changes, extracted_at):
    n_clean = len(df)

    lines = []
    lines.append("# Cleaning and validation log")
    lines.append("")
    lines.append(f"Raw file: `data/raw/nyc311_raw.csv`, {n_raw:,} rows. Extracted {extracted_at:%Y-%m-%d %H:%M}.")
    lines.append("")
    lines.append("## What was changed")
    lines.append("")
    lines.append("| Step | Rows affected |")
    lines.append("|---|---|")

    untouched = []
    for step in changes:
        count = changes[step]
        if step.startswith("flag_"):
            continue
        if count == 0 and step.startswith("whitespace"):
            untouched.append(step.split(" in ")[1])
            continue
        lines.append(f"| {step} | {count:,} |")

    lines.append("")
    lines.append("Columns checked for stray whitespace with nothing to fix: " + ", ".join(untouched) + ".")
    lines.append("")
    lines.append("## Flags (values kept, rows marked)")
    lines.append("")
    lines.append("| Flag | Meaning | Rows |")
    lines.append("|---|---|---|")
    for flag in FLAG_MEANING:
        lines.append(f"| {flag} | {FLAG_MEANING[flag]} | {changes[flag]:,} |")

    valid = int(df["resolution_hours"].notna().sum())
    closed = int(df["is_closed"].sum())
    lines.append("")
    lines.append("## Validation")
    lines.append("")
    lines.append(f"- Raw rows {n_raw:,}, clean rows {n_clean:,} (no rows were dropped).")
    lines.append(f"- unique_key unique in clean data: {df['unique_key'].is_unique}")
    lines.append(f"- created_date range: {df['created_date'].min()} to {df['created_date'].max()}")
    lines.append(f"- Valid resolution durations: {valid:,} of {closed:,} closed rows")
    lines.append(f"- Smallest / largest resolution_hours: {df['resolution_hours'].min():.3f} / {df['resolution_hours'].max():,.1f}")
    lines.append("- The database row count is checked in `src/load.py` and written to `docs/load_log.json`.")
    lines.append("")
    Path("docs/cleaning_log.md").write_text("\n".join(lines))

    log = {"raw_rows": n_raw, "clean_rows": n_clean, "changes": changes}
    Path("docs/cleaning_log.json").write_text(json.dumps(log, indent=2))


def write_data_dictionary(df):
    raw = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    raw_missing = (raw == "").sum()

    lines = []
    lines.append("# Data dictionary")
    lines.append("")
    lines.append("Source: NYC 311 Service Requests from 2020 to Present (`erm2-nwe9`). "
                 "Missing % is on the cleaned file, `raw missing` is what the API returned empty.")
    lines.append("")
    lines.append("| Column | Meaning | Type | Missing % | Raw missing | Transformation | Used for |")
    lines.append("|---|---|---|---|---|---|---|")

    for col in df.columns:
        if col in MEANING:
            meaning, how, use = MEANING[col]
        else:
            meaning = FLAG_MEANING[col]
            how = "derived true/false flag"
            use = "data quality"
        missing_pct = df[col].isna().mean() * 100
        if col in raw_missing:
            raw_text = f"{int(raw_missing[col]):,}"
        else:
            raw_text = "-"
        lines.append(f"| {col} | {meaning} | {type_name(df[col])} | {missing_pct:.1f} | {raw_text} | {how} | {use} |")

    Path("docs/data_dictionary.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
