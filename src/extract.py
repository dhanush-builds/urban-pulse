import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
RAW_DIR = Path("data/raw")
PART_DIR = RAW_DIR / "parts"

START = date(2025, 1, 1)
END = date(2025, 6, 30)
ROW_TARGET = 110_000

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
    high = min(next_month, END + timedelta(days=1))
    low_text = str(low) + "T00:00:00"
    high_text = str(high) + "T00:00:00"
    tests = []
    for ending in KEY_ENDINGS:
        tests.append("unique_key like '%" + ending + "'")
    key_text = " OR ".join(tests)
    return "created_date >= '" + low_text + "' AND created_date < '" + high_text + "' AND (" + key_text + ")"


def get_page(params, headers):
    for attempt in range(1, MAX_TRIES + 1):
        try:
            r = requests.get(URL, params=params, headers=headers, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(5 * attempt)
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
        else:
            df, where = pull_month(m, headers)
            df.to_csv(part, index=False)
        month_info.append({"month": f"{m:%Y-%m}", "rows": len(df), "where": where})
        total += len(df)
        if total >= ROW_TARGET:
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


if __name__ == "__main__":
    main()
