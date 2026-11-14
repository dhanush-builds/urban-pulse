"""Pull a sample of NYC 311 requests from the Socrata API into data/raw/.

Run from the project root:  python src/extract.py
Each month is saved on its own in data/raw/parts/, so if the run dies
you can start it again and it carries on with the missing months.
"""
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

# Jan to Jun 2025. The full window has ~1.76M requests, we want roughly 100k.
START = date(2025, 1, 1)
END = date(2025, 6, 30)
ROW_TARGET = 110_000

# unique_key is a running number, so its last two digits have nothing to do
# with date, agency or complaint type. Six endings out of 100 gives ~6%.
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


def month_starts(first, last):
    d = date(first.year, first.month, 1)
    while d <= last:
        yield d
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def where_clause(month_start):
    next_month = date(month_start.year + (month_start.month == 12), month_start.month % 12 + 1, 1)
    lo = max(month_start, START)
    # END is inclusive, so the upper bound is the day after it
    hi = min(next_month, date.fromordinal(END.toordinal() + 1))
    endings = " OR ".join(f"unique_key like '%{e}'" for e in KEY_ENDINGS)
    return (f"created_date >= '{lo}T00:00:00' AND created_date < '{hi}T00:00:00' "
            f"AND ({endings})")


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
    rows, offset = [], 0
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
    # the API leaves out keys that are null, so make sure every column exists
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
    for m in month_starts(START, END):
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

    raw = pd.concat(
        [pd.read_csv(PART_DIR / f"{i['month']}.csv", dtype=str, keep_default_na=False)
         for i in month_info],
        ignore_index=True,
    )
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
