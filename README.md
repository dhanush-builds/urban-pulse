# Urban Pulse: NYC 311 complaint analytics

GUVI capstone project. It pulls NYC 311 service requests from the NYC Open Data API, cleans them, checks the statistics, stores them in a database, answers 15 analyst questions in SQL and Python, and shows the results in a Streamlit dashboard with five KPIs.

Data: [311 Service Requests from 2020 to Present](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9) (`erm2-nwe9`).

**Database note.** The brief suggests MySQL. This version runs on PostgreSQL 17 (in Docker) because that is the database used in the course sessions. The schema is plain SQL; the queries use `PERCENTILE_CONT`, `MODE()` and `FILTER`, which would need rewriting for MySQL (window functions with `PERCENT_RANK`, `ROW_NUMBER`, and `CASE` instead of `FILTER`).

## Folder layout

```
src/extract.py      API extraction, paging and retries  -> data/raw/
src/clean.py        cleaning, flags, derived fields     -> data/clean/, docs/cleaning_log.md, docs/data_dictionary.md
src/stats.py        statistics, skewness, IQR outliers  -> docs/stats_report.md, docs/figures/
src/load.py         staging table, validation, publish  -> PostgreSQL, docs/load_log.json
src/db.py           connection settings from .env
sql/schema.sql      table and indexes
sql/analysis.sql    the 15 analyst queries
notebooks/eda.ipynb the 15 tasks with charts and interpretation
app/                Streamlit dashboard (Overview + 4 analyst pages)
docs/               data dictionary, cleaning log, extraction log, load log, stats report, final report
```

## Run it

Python 3.12 or newer and Docker.

```bash
# 1. database (pick your own password)
docker run --name urban-pulse-pg -e POSTGRES_PASSWORD=choose_one -p 5433:5432 -d postgres:17

# 2. python environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # put the same password in DB_PASSWORD

# 3. pipeline, in this order, from the project root
.venv/bin/python src/extract.py     # about 5 minutes, no API key needed
.venv/bin/python src/clean.py
.venv/bin/python src/stats.py
.venv/bin/python src/load.py        # creates urban_pulse_db and validates the load

# 4. dashboard
.venv/bin/streamlit run app/Overview.py
```

The notebook runs from its own folder: `cd notebooks && ../.venv/bin/jupyter notebook eda.ipynb`.
To run the SQL by hand: `docker exec -i urban-pulse-pg psql -U postgres -d urban_pulse_db < sql/analysis.sql`.

`extract.py` saves each month separately in `data/raw/parts/`. If it stops half way, run it again and it carries on.

## Data window and sample

- Requests created 1 January to 30 June 2025 (about 1.76 million in the API for that window).
- We keep every request whose `unique_key` ends in 12, 29, 37, 58, 64 or 91, about 6%. The key is a running number, so its last digits are unrelated to date, agency or complaint type. Sorting by date and taking the first 100,000 would have given only the first ten days of January.
- Result: **105,540 rows**, 25 source fields, no duplicate keys. Extracted 14 November 2026, so status and closed dates are as of that day. Exact queries are in `docs/extraction_log.json`.

## Load validation

Source rows, cleaned rows and database rows all match at 105,540. The loader checks counts, unique keys, the resolution_hours count and five random rows against the CSV before it swaps the staging table in. Details in `docs/load_log.json`.

## The five KPIs

| KPI | Definition |
|---|---|
| Total requests | distinct `unique_key` in the filtered data |
| Recorded closure | share of filtered rows with a closed date |
| Open requests | filtered rows with no closed date |
| Median resolution | median hours from created to closed, valid durations only |
| Over 72 hours | share of valid durations above 72 hours |

Closure means a closed date is recorded. It does not mean the citizen was satisfied. The 72-hour line is our own cut-off, not an official service standard.

## Findings in short

- Half of all requests go to NYPD (46%), then HPD (22%). Illegal Parking, Residential Noise and Heat/Hot Water are the biggest complaint types.
- Resolution time is heavily right-skewed: median 7.8 hours, mean 261.8 hours, skewness 6.7. 23.9% of valid durations are over 72 hours.
- Slow and frequent: Unsanitary Condition and Door/Window (both HPD housing complaints).
- One police-station coordinate holds 2.7% of rows, so the location data needs care.

Full write-up: [docs/final_report.md](docs/final_report.md).

## Limitations

Reported requests only, a 6% systematic sample of six months, status as of the extraction date, closure is a recorded date and not verified resolution, and agencies handle different work so they should not be ranked on these numbers.
