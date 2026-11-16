import json
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("data/raw/nyc311_raw.csv")
OUT = Path("data/clean/nyc311_clean.csv")

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
        edited = (before != df[col]) & df[col].notna()
        changes["whitespace fixed in " + col] = int(edited.sum())
    return df


def use_commonest_spelling(df, col, changes):
    lower = df[col].str.lower()
    best = {}
    for word in lower.dropna().unique():
        spellings = df.loc[lower == word, col]
        best[word] = spellings.value_counts().index[0]
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
    district = pd.to_numeric(df["council_district"], errors="coerce")
    df["council_district"] = district.astype("Int64")

    bad_zip = df["incident_zip"].notna() & ~df["incident_zip"].str.fullmatch(r"\d{5}", na=False)
    changes["invalid zip set to null"] = int(bad_zip.sum())
    df.loc[bad_zip, "incident_zip"] = np.nan
    return df


def add_flags(df, changes, extracted_at):
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

    point = df["latitude"].astype(str) + "," + df["longitude"].astype(str)
    rows_at_point = point.map(point.value_counts())
    df["flag_repeated_coords"] = (rows_at_point > 1000) & ~df["flag_missing_coords"]

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

    has_hours = df["resolution_hours"].notna()
    df["is_over_72h"] = None
    df.loc[has_hours, "is_over_72h"] = df["resolution_hours"] > 72

    created = df["created_date"]
    df["created_year"] = created.dt.year
    df["created_month"] = created.dt.month
    df["created_year_month"] = created.dt.strftime("%Y-%m")
    df["created_weekday"] = created.dt.day_name()
    df["created_weekday_num"] = created.dt.day_of_week
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

    log = {"raw_rows": n_raw, "clean_rows": len(df), "changes": changes}
    Path("docs/cleaning_log.json").write_text(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
