import json
import os
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
RAW_DIR = Path("data/raw")
PART_DIR = RAW_DIR / "parts"

# January to June 2025
START = date(2025, 1, 1)
END = date(2025, 6, 30)
ROW_TARGET = 110_000

# we keep requests whose unique_key ends in one of these numbers (about 6% of rows)
KEY_ENDINGS = ["12", "29", "37", "58", "64", "91"]

FIELDS = [
    "unique_key", "created_date", "closed_date", "due_date",
    "agency", "agency_name", "complaint_type", "descriptor",
    "location_type", "address_type", "incident_zip", "incident_address",
    "street_name", "city", "borough", "status",
    "resolution_description", "resolution_action_updated_date",
    "community_board", "council_district", "police_precinct", "bbl",
    "open_data_channel_type", "latitude", "longitude",
]

PAGE_SIZE = 5000
TIMEOUT = 90
MAX_TRIES = 6


def next_month_start(d):
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def list_months():
    months = []
    d = date(START.year, START.month, 1)
    while d <= END:
        months.append(d)
        d = next_month_start(d)
    return months


def where_clause(month_start):
    next_month = next_month_start(month_start)
    low = max(month_start, START)
    # END is included, so the upper limit is the day after it
    high = min(next_month, date.fromordinal(END.toordinal() + 1))
    endings = []
    for e in KEY_ENDINGS:
        endings.append(f"unique_key like '%{e}'")
    endings_text = " OR ".join(endings)
    return (f"created_date >= '{low}T00:00:00' AND created_date < '{high}T00:00:00' "
            f"AND ({endings_text})")


def get_page(params, headers):
    for attempt in range(1, MAX_TRIES + 1):
        try:
            r = requests.get(URL, params=params, headers=headers, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
            print(f"  http {r.status_code}, try {attempt}")
        except requests.RequestException as e:
            print(f"  {type(e).__name__}, try {attempt}")
        time.sleep(min(2 ** attempt, 60))
    raise RuntimeError("API kept failing, giving up on this page")


def pull_month(month_start, headers):
    where = where_clause(month_start)
    rows = []
    offset = 0
    while True:
        params = {
            "$select": ",".join(FIELDS),
            "$where": where,
            "$order": "created_date,unique_key",
            "$limit": PAGE_SIZE,
            "$offset": offset,
        }
        page = get_page(params, headers)
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    # the API leaves out empty fields, so add every column back
    return pd.DataFrame(rows).reindex(columns=FIELDS), where


def main():
    PART_DIR.mkdir(parents=True, exist_ok=True)
    headers = {}
    token = os.getenv("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token

    started = datetime.now()
    month_info = []
    total = 0
    for m in list_months():
        part = PART_DIR / f"{m:%Y-%m}.csv"
        if part.exists():
            df = pd.read_csv(part, dtype=str, keep_default_na=False)
            where = where_clause(m)
            print(f"{m:%Y-%m}: reusing {len(df):,} rows from disk")
        else:
            print(f"{m:%Y-%m}: downloading...")
            df, where = pull_month(m, headers)
            df.to_csv(part, index=False)
            print(f"{m:%Y-%m}: {len(df):,} rows")
        month_info.append({"month": f"{m:%Y-%m}", "rows": len(df), "where": where})
        total += len(df)
        if total >= ROW_TARGET:
            print("row target reached, stopping")
            break

    all_parts = []
    for info in month_info:
        part = PART_DIR / (info["month"] + ".csv")
        all_parts.append(pd.read_csv(part, dtype=str, keep_default_na=False))
    raw = pd.concat(all_parts, ignore_index=True)
    raw.to_csv(RAW_DIR / "nyc311_raw.csv", index=False)

    log = {
        "extracted_at": started.isoformat(timespec="seconds"),
        "endpoint": URL,
        "window": [str(START), str(END)],
        "sampling": f"unique_key ending in {', '.join(KEY_ENDINGS)}",
        "order": "created_date, unique_key",
        "page_size": PAGE_SIZE,
        "fields": FIELDS,
        "row_target": ROW_TARGET,
        "rows_received": len(raw),
        "duplicate_keys": int(raw["unique_key"].duplicated().sum()),
        "first_created": raw["created_date"].min(),
        "last_created": raw["created_date"].max(),
        "months": month_info,
        "limits": [
            "status and closed_date are as of the extraction date",
            "sample is systematic by unique_key ending, not random",
            "the API omits null fields, they were re-added as empty",
        ],
    }
    Path("docs").mkdir(exist_ok=True)
    with open("docs/extraction_log.json", "w") as f:
        json.dump(log, f, indent=2)
    print(f"done: {len(raw):,} rows -> data/raw/nyc311_raw.csv")


if __name__ == "__main__":
    main()
