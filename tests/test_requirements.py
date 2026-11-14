"""Checks the data side of the brief: extraction, cleaning, statistics, MySQL/Postgres load, 15 SQL tasks.

Run from the project root:  .venv/bin/python -m pytest tests -q
Needs the pipeline to have run once and the database container to be up.
"""
import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest
from scipy import stats
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent


def sql(engine, query, **params):
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params=params)


# ---------------------------------------------------------------- 5. extraction

def test_extraction_log_records_what_the_brief_asks(extraction_log):
    for key in ["extracted_at", "endpoint", "window", "order", "page_size", "fields",
                "rows_received", "limits", "months"]:
        assert key in extraction_log, key
    assert "data.cityofnewyork.us/resource/erm2-nwe9" in extraction_log["endpoint"]
    assert all("where" in m for m in extraction_log["months"])


def test_about_100k_rows_and_25_fields(raw, extraction_log):
    assert 90_000 <= len(raw) <= 120_000
    assert len(raw.columns) == len(extraction_log["fields"]) == 25
    assert len(raw) == extraction_log["rows_received"]


def test_core_fields_are_present(raw):
    core = ["unique_key", "created_date", "closed_date", "due_date", "agency", "complaint_type",
            "borough", "status", "latitude", "longitude"]
    assert set(core) <= set(raw.columns)


def test_raw_is_kept_separate_and_untouched(raw, clean):
    # raw is all text with empty strings, clean has real types
    assert (raw == "").any().any()
    assert pd.api.types.is_datetime64_any_dtype(clean["created_date"])
    assert (ROOT / "data/raw/parts").is_dir()


def test_sample_is_inside_the_stated_window(raw, extraction_log):
    created = pd.to_datetime(raw["created_date"])
    lo, hi = pd.Timestamp(extraction_log["window"][0]), pd.Timestamp(extraction_log["window"][1])
    assert created.min() >= lo and created.max() < hi + pd.Timedelta(days=1)


# ---------------------------------------------------------------- 7. cleaning

def test_no_rows_lost_and_keys_unique(raw, clean):
    assert len(raw) == len(clean)
    assert clean["unique_key"].is_unique
    assert set(raw["unique_key"].astype(int)) == set(clean["unique_key"])


def test_is_closed_follows_closed_date(clean):
    assert (clean["is_closed"] == clean["closed_date"].notna()).all()


def test_resolution_hours_only_for_valid_closed_rows(clean):
    has_hours = clean["resolution_hours"].notna()
    assert (clean.loc[has_hours, "closed_date"].notna()).all()
    assert (clean.loc[has_hours, "resolution_hours"] >= 0).all()
    # closed before created must not get a duration
    assert not clean.loc[clean["flag_closed_before_created"], "resolution_hours"].notna().any()
    # and the number is really the difference in hours
    check = clean[has_hours].head(2000)
    diff = (check["closed_date"] - check["created_date"]).dt.total_seconds() / 3600
    assert ((diff - check["resolution_hours"]).abs() < 0.001).all()


def test_invalid_dates_are_flagged_not_dropped(raw, clean):
    created = pd.to_datetime(raw["created_date"])
    closed = pd.to_datetime(raw["closed_date"].replace("", None))
    assert int((closed < created).sum()) == int(clean["flag_closed_before_created"].sum())
    status_no_date = ((raw["status"] == "Closed") & (raw["closed_date"] == "")).sum()
    assert int(status_no_date) == int(clean["flag_closed_status_no_date"].sum())


def test_temporal_fields_match_created_date(clean):
    d = clean["created_date"]
    assert (clean["created_hour"] == d.dt.hour).all()
    assert (clean["created_weekday_num"] == d.dt.day_of_week).all()
    assert (clean["created_year_month"] == d.dt.strftime("%Y-%m")).all()
    assert (clean["created_month"] == d.dt.month).all()


def test_over_72h_flag_matches_hours(clean):
    valid = clean["resolution_hours"].notna()
    assert clean.loc[~valid, "is_over_72h"].isna().all()
    expected = clean.loc[valid, "resolution_hours"] > 72
    assert (clean.loc[valid, "is_over_72h"].astype(bool) == expected).all()


def test_text_is_tidy(clean):
    for col in ["complaint_type", "borough", "agency"]:
        s = clean[col].dropna()
        assert (s == s.str.strip()).all()
        assert not s.str.contains(r"\s\s").any()
    # case variants merged: one spelling per lower-case value
    for col in ["complaint_type", "borough"]:
        s = clean[col].dropna()
        assert s.groupby(s.str.lower()).nunique().max() == 1


def test_data_dictionary_covers_every_column(clean):
    doc = (ROOT / "docs/data_dictionary.md").read_text()
    for col in clean.columns:
        assert f"| {col} |" in doc, col
    for word in ["Meaning", "Type", "Missing", "Transformation", "Used for"]:
        assert word in doc


def test_cleaning_log_has_counts_and_validation():
    log = (ROOT / "docs/cleaning_log.md").read_text()
    assert "Flags" in log and "Validation" in log
    assert json.loads((ROOT / "docs/cleaning_log.json").read_text())["clean_rows"] > 0


# ---------------------------------------------------------------- 8. statistics

def test_stats_summary_matches_recomputation(clean):
    s = json.loads((ROOT / "docs/stats_summary.json").read_text())
    h = clean["resolution_hours"].dropna()
    q1, q3 = h.quantile(0.25), h.quantile(0.75)
    iqr = q3 - q1
    assert s["n_valid"] == len(h)
    assert s["median"] == pytest.approx(h.median(), abs=0.01)
    assert s["mean"] == pytest.approx(h.mean(), abs=0.01)
    assert s["iqr"] == pytest.approx(iqr, abs=0.01)
    assert s["high_fence"] == pytest.approx(q3 + 1.5 * iqr, abs=0.01)
    assert s["low_fence"] == pytest.approx(q1 - 1.5 * iqr, abs=0.01)
    assert s["n_above_high_fence"] == int((h > q3 + 1.5 * iqr).sum())
    assert s["skewness"] == pytest.approx(stats.skew(h), abs=0.01)
    assert s["mean"] > s["median"]          # right skew, the report relies on this


def test_stats_outputs_exist():
    for name in ["resolution_hist.png", "resolution_boxplot.png"]:
        assert (ROOT / "docs/figures" / name).stat().st_size > 5000
    report = (ROOT / "docs/stats_report.md").read_text()
    for word in ["Mean", "Median", "Mode", "Variance", "IQR", "Skewness", "fence"]:
        assert word in report, word


# ---------------------------------------------------------------- 9. database load

def test_row_counts_match_across_source_clean_and_database(engine, raw, clean):
    n_db = sql(engine, "select count(*) n from service_requests").loc[0, "n"]
    assert len(raw) == len(clean) == n_db
    distinct = sql(engine, "select count(distinct unique_key) n from service_requests").loc[0, "n"]
    assert distinct == n_db


def test_load_log_agrees_with_database(engine):
    log = json.loads((ROOT / "docs/load_log.json").read_text())
    assert log["clean_csv_rows"] == log["staging_rows"] == log["final_rows"]
    assert log["sample_rows_matching_csv"] == "5/5"


def test_no_staging_table_left_behind(engine):
    tables = sql(engine, "select table_name from information_schema.tables where table_schema = 'public'")
    assert "service_requests" in set(tables["table_name"])
    assert "service_requests_staging" not in set(tables["table_name"])


def test_table_columns_match_the_clean_file(engine, clean):
    cols = sql(engine, "select column_name from information_schema.columns where table_name = 'service_requests'")
    assert set(cols["column_name"]) == set(clean.columns)


def test_primary_key_and_indexes(engine):
    idx = sql(engine, "select indexname from pg_indexes where tablename = 'service_requests'")["indexname"].tolist()
    assert "service_requests_pkey" in idx
    assert {"idx_sr_created", "idx_sr_agency", "idx_sr_complaint", "idx_sr_borough", "idx_sr_ym"} <= set(idx)


def test_database_values_equal_csv_aggregates(engine, clean):
    row = sql(engine, "select sum(resolution_hours) s, count(resolution_hours) n, sum(is_closed::int) c, "
                      "sum(flag_closed_before_created::int) f from service_requests").iloc[0]
    assert row["n"] == clean["resolution_hours"].notna().sum()
    assert row["s"] == pytest.approx(clean["resolution_hours"].sum(), rel=1e-6)
    assert row["c"] == clean["is_closed"].sum()
    assert row["f"] == clean["flag_closed_before_created"].sum()


def test_spot_check_random_rows_against_csv(engine, clean):
    for _, r in clean.sample(25, random_state=7).iterrows():
        row = sql(engine, "select agency, complaint_type, borough, status, created_date from service_requests "
                          "where unique_key = :k", k=int(r["unique_key"])).iloc[0]
        assert row["agency"] == r["agency"]
        assert row["complaint_type"] == r["complaint_type"]
        assert row["status"] == r["status"]
        assert pd.Timestamp(row["created_date"]) == r["created_date"]


# ---------------------------------------------------------------- 10. the 15 analyst tasks

def test_all_15_tasks_exist(sql_tasks):
    assert sorted(sql_tasks) == list(range(1, 16))


@pytest.mark.parametrize("task", range(1, 16))
def test_every_task_query_runs_and_returns_rows(engine, sql_tasks, task):
    for statement in sql_tasks[task]:
        assert len(sql(engine, statement)) > 0, f"task {task} returned nothing"


def test_task_1_total_volume(engine, sql_tasks, clean):
    assert sql(engine, sql_tasks[1][0]).iloc[0, 0] == len(clean)


def test_task_2_top_complaints(engine, sql_tasks, clean):
    got = sql(engine, sql_tasks[2][0])
    expect = clean["complaint_type"].value_counts().head(10)
    assert got["complaint_type"].tolist() == expect.index.tolist()
    assert got["requests"].tolist() == expect.tolist()


def test_tasks_3_4_5_7_counts(engine, sql_tasks, clean):
    for task, col in [(3, "agency"), (4, "borough"), (7, "status")]:
        got = sql(engine, sql_tasks[task][0]).set_index(col)["requests"].to_dict()
        assert got == clean[col].value_counts().to_dict(), col
    monthly = sql(engine, sql_tasks[5][0]).set_index("month")["requests"].to_dict()
    assert monthly == clean["created_year_month"].value_counts().to_dict()


def test_task_6_weekday_hour_grid(engine, sql_tasks, clean):
    got = sql(engine, sql_tasks[6][0])
    assert got["requests"].sum() == len(clean)
    expect = clean.groupby(["created_weekday_num", "created_hour"]).size()
    merged = got.set_index(["created_weekday_num", "created_hour"])["requests"]
    assert merged.equals(expect.astype(merged.dtype))


def test_task_8_descriptive_stats(engine, sql_tasks, clean):
    got = sql(engine, sql_tasks[8][0]).iloc[0]
    h = clean["resolution_hours"].dropna()
    assert got["n"] == len(h)
    assert float(got["mean"]) == pytest.approx(h.mean(), abs=0.01)
    assert float(got["median"]) == pytest.approx(h.median(), abs=0.01)
    assert float(got["q1"]) == pytest.approx(h.quantile(0.25), abs=0.01)
    assert float(got["std_dev"]) == pytest.approx(h.std(), abs=0.1)


def test_tasks_9_10_medians(engine, sql_tasks, clean):
    for task, col in [(9, "complaint_type"), (10, "agency")]:
        got = sql(engine, sql_tasks[task][0])
        h = clean.dropna(subset=["resolution_hours"])
        g = h.groupby(col)["resolution_hours"].agg(["median", "size"])
        for _, row in got.head(5).iterrows():
            name = row[col]
            assert row["n"] == g.loc[name, "size"]
            assert float(row["median_hours"]) == pytest.approx(g.loc[name, "median"], abs=0.06)


def test_task_11_outliers_add_up(engine, sql_tasks, clean):
    got = sql(engine, sql_tasks[11][0])
    h = clean["resolution_hours"].dropna()
    fence = h.quantile(0.75) + 1.5 * (h.quantile(0.75) - h.quantile(0.25))
    small_groups = h[clean.loc[h.index, "agency"].isin(got["agency"])]
    assert got["above_high_fence"].sum() == int((small_groups > fence).sum())


def test_task_12_skewness_and_bands(engine, sql_tasks, clean):
    skew = sql(engine, sql_tasks[12][0]).iloc[0, 0]
    # SQL gives population skewness, scipy default is the same
    assert float(skew) == pytest.approx(stats.skew(clean["resolution_hours"].dropna()), abs=0.01)
    bands = sql(engine, sql_tasks[12][1])
    assert bands["requests"].sum() == clean["resolution_hours"].notna().sum()


def test_task_13_geography_excludes_placeholder(engine, sql_tasks, clean):
    cover = sql(engine, sql_tasks[13][0]).set_index("borough")
    assert cover["requests"].sum() == len(clean)
    assert cover["with_coordinates"].sum() == clean["latitude"].notna().sum()
    grid = sql(engine, sql_tasks[13][1])
    usable = (~clean["flag_missing_coords"]) & (~clean["flag_coords_outside_nyc"]) & (~clean["flag_repeated_coords"])
    assert grid["requests"].max() < usable.sum()
    assert not (clean["flag_repeated_coords"].sum() == 0)      # the placeholder point exists


def test_task_14_closure_rates(engine, sql_tasks, clean):
    got = sql(engine, sql_tasks[14][0])
    by_agency = clean.groupby("agency")["is_closed"].mean() * 100
    row = got[(got["grouping"] == "agency")].iloc[0]
    assert float(row["closure_pct"]) == pytest.approx(by_agency[row["name"]], abs=0.06)


def test_task_15_priority_categories_are_above_both_cutoffs(engine, sql_tasks, clean):
    got = sql(engine, sql_tasks[15][0])
    h = clean.dropna(subset=["resolution_hours"])
    g = h.groupby("complaint_type")["resolution_hours"].agg(["size", "median"])
    g = g[g["size"] >= 100]
    vol_cut, dur_cut = g["size"].quantile(0.75), g["median"].quantile(0.75)
    expect = set(g[(g["size"] >= vol_cut) & (g["median"] >= dur_cut)].index)
    assert set(got["complaint_type"]) == expect


# ---------------------------------------------------------------- credentials and deliverables

def test_no_credentials_in_git():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert ".env" not in tracked
    assert not any(t.startswith("data/raw/") or t.startswith("data/clean/") for t in tracked if not t.endswith(".gitkeep"))
    env = (ROOT / ".env").read_text() if (ROOT / ".env").exists() else ""
    password = [l.split("=", 1)[1].strip() for l in env.splitlines() if l.startswith("DB_PASSWORD=")]
    if password and password[0]:
        found = subprocess.run(["git", "grep", "-l", password[0]], cwd=ROOT, capture_output=True, text=True).stdout
        assert found == ""
        history = subprocess.run(["git", "log", "-S" + password[0], "--oneline"], cwd=ROOT,
                                 capture_output=True, text=True).stdout
        assert history == ""


def test_no_password_literals_in_code():
    bad = []
    for path in list((ROOT / "src").glob("*.py")) + list((ROOT / "app").rglob("*.py")):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            low = line.lower().replace(" ", "")
            if ('password="' in low or "password='" in low) and "getenv" not in low and "os.environ" not in low:
                bad.append(f"{path.name}:{n}")
    assert bad == []


def test_deliverable_files_exist():
    needed = ["README.md", "requirements.txt", ".env.example", "src/extract.py", "src/clean.py", "src/stats.py",
              "src/load.py", "sql/schema.sql", "sql/analysis.sql", "notebooks/eda.ipynb", "app/Overview.py",
              "docs/data_dictionary.md", "docs/cleaning_log.md", "docs/extraction_log.json", "docs/load_log.json",
              "docs/stats_report.md", "docs/final_report.md"]
    missing = [f for f in needed if not (ROOT / f).exists()]
    assert missing == []


def test_notebook_has_15_executed_tasks_without_errors():
    import nbformat
    nb = nbformat.read(ROOT / "notebooks/eda.ipynb", as_version=4)
    headings = [c.source for c in nb.cells if c.cell_type == "markdown" and c.source.startswith("## ")]
    numbered = [h for h in headings if h[3:].split(".")[0].isdigit()]
    assert len(numbered) == 15
    code = [c for c in nb.cells if c.cell_type == "code"]
    assert all(c.get("outputs") is not None for c in code)
    errors = [o for c in code for o in c["outputs"] if o.output_type == "error"]
    assert errors == []
    text = "\n".join(c.source for c in nb.cells if c.cell_type == "markdown")
    assert text.count("**Observed.**") >= 15 and text.count("**Careful reading.**") >= 15
    charts = sum(1 for c in code for o in c["outputs"] if "image/png" in o.get("data", {}))
    assert charts >= 15


def test_limitations_are_documented():
    report = (ROOT / "docs/final_report.md").read_text().lower()
    for phrase in ["reported requests", "closure", "72", "sample", "extract"]:
        assert phrase in report, phrase
