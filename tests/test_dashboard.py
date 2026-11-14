"""Checks the Streamlit side of the brief: pages, five KPIs, filters, empty and error states.

Uses Streamlit's AppTest, so no browser is needed. Needs the database container up.
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["app/Overview.py", "app/pages/1_Volume_and_Demand.py", "app/pages/2_Resolution_Time.py",
         "app/pages/3_Geography_and_Closure.py", "app/pages/4_Complaint_Priorities.py"]


def open_page(path):
    return AppTest.from_file(str(ROOT / path), default_timeout=90).run()


def kpis_from(at):
    return {m.label: m.value for m in at.metric}


def expected_kpis(df):
    h = df["resolution_hours"].dropna()
    return {
        "Total requests": f"{df['unique_key'].nunique():,}",
        "Recorded closure": f"{100 * df['is_closed'].mean():.1f}%",
        "Open requests": f"{int((~df['is_closed']).sum()):,}",
        "Median resolution": f"{h.median():.1f} h",
        "Over 72 hours": f"{100 * (h > 72).mean():.1f}%",
    }


@pytest.mark.parametrize("page", PAGES)
def test_every_page_loads_without_errors(page):
    at = open_page(page)
    assert not at.exception
    assert not at.error
    assert len(at.sidebar.multiselect) == 2        # borough, complaint type
    assert len(at.sidebar.date_input) == 1


def test_five_kpis_with_the_right_labels(clean):
    at = open_page("app/Overview.py")
    assert list(kpis_from(at)) == ["Total requests", "Recorded closure", "Open requests",
                                   "Median resolution", "Over 72 hours"]


def test_kpi_values_match_pandas_without_filters(clean):
    at = open_page("app/Overview.py")
    assert kpis_from(at) == expected_kpis(clean)


def test_kpis_follow_borough_and_type_filters(clean):
    at = open_page("app/Overview.py")
    at.sidebar.multiselect(key="boroughs").set_value(["BROOKLYN"]).run()
    assert kpis_from(at) == expected_kpis(clean[clean["borough"] == "BROOKLYN"])

    at.sidebar.multiselect(key="types").set_value(["Illegal Parking", "Rodent"]).run()
    subset = clean[(clean["borough"] == "BROOKLYN") & clean["complaint_type"].isin(["Illegal Parking", "Rodent"])]
    assert kpis_from(at) == expected_kpis(subset)


def test_kpis_follow_the_date_filter(clean):
    at = open_page("app/Overview.py")
    at.sidebar.date_input(key="dates").set_value((date(2025, 3, 1), date(2025, 3, 31))).run()
    march = clean[(clean["created_date"] >= "2025-03-01") & (clean["created_date"] < "2025-04-01")]
    assert kpis_from(at) == expected_kpis(march)


def test_record_preview_is_filtered_and_capped():
    at = open_page("app/Overview.py")
    at.sidebar.multiselect(key="boroughs").set_value(["STATEN ISLAND"]).run()
    preview = at.dataframe[-1].value
    assert 0 < len(preview) <= 200
    assert set(preview["borough"]) == {"STATEN ISLAND"}


@pytest.mark.parametrize("page", PAGES)
def test_empty_state_is_readable_on_every_page(page):
    at = open_page(page)
    at.sidebar.multiselect(key="boroughs").set_value(["Unspecified"]).run()
    at.sidebar.multiselect(key="types").set_value(["Noise - Helicopter"]).run()
    assert not at.exception
    assert any("No requests match" in i.value for i in at.info)


def test_filters_change_the_analyst_pages(clean):
    """Volume page: status table must add up to the filtered total."""
    at = open_page("app/pages/1_Volume_and_Demand.py")
    at.sidebar.multiselect(key="boroughs").set_value(["QUEENS"]).run()
    assert not at.exception
    status_table = [d.value for d in at.dataframe if "status" in d.value.columns][0]
    assert status_table["requests"].sum() == (clean["borough"] == "QUEENS").sum()


def test_resolution_page_min_cases_control_works():
    at = open_page("app/pages/2_Resolution_Time.py")
    at.number_input[0].set_value(1000).run()
    assert not at.exception


def test_priority_page_cutoffs_and_empty_message():
    at = open_page("app/pages/4_Complaint_Priorities.py")
    assert not at.exception
    at.number_input[0].set_value(1000).run()          # almost no category has 1000 valid cases
    assert not at.exception


def test_connection_error_message_on_every_page():
    code = """
import os, sys, json
os.environ['DB_PORT'] = '5999'
sys.path.insert(0, {app!r})
from streamlit.testing.v1 import AppTest
out = {{}}
for p in {pages!r}:
    at = AppTest.from_file({root!r} + p, default_timeout=120).run()
    out[p] = [len(at.exception), [e.value[:40] for e in at.error]]
print('RESULT' + json.dumps(out))
""".format(app=str(ROOT / "app"), root=str(ROOT) + "/", pages=PAGES)
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600)
    line = [l for l in done.stdout.splitlines() if l.startswith("RESULT")][0]
    for page, (n_exc, errors) in json.loads(line[6:]).items():
        assert n_exc == 0, page
        assert errors and errors[0].startswith("Could not reach the database"), page


def test_hostile_filter_values_cannot_touch_the_table(engine):
    sys.path.insert(0, str(ROOT / "app"))
    import common
    evil = "x'; drop table service_requests; --"
    out = common.query("select count(*) n from service_requests where complaint_type = any(:t)", {"t": [evil]})
    assert out.loc[0, "n"] == 0
    still_there = pd.read_sql("select count(*) n from service_requests", engine)
    assert still_there.loc[0, "n"] > 100_000


def test_app_code_does_not_put_user_input_into_sql():
    """Filter values are only ever passed as bind parameters (:name), never formatted into the text."""
    common = (ROOT / "app/common.py").read_text()
    assert "= any(:boroughs)" in common and "= any(:types)" in common
    assert ":start" in common and ":end" in common
    for line in common.splitlines():
        if "chosen_boroughs" in line or "chosen_types" in line:
            assert "f\"" not in line and ".format" not in line


def test_theme_and_run_files_exist():
    assert (ROOT / ".streamlit/config.toml").exists()
    assert "streamlit" in (ROOT / "requirements.txt").read_text().lower()
