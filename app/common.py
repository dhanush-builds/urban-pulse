"""Shared pieces for every dashboard page: database, filters, KPIs."""
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))
from db import get_engine  # noqa: E402

BLUE = "#1f5f8b"
RUST = "#c8553d"
THRESHOLD_HOURS = 72   # our own cut-off, not an official service standard

# Streamlit Cloud keeps credentials in st.secrets, locally they come from .env
try:
    for key in ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]:
        if key in st.secrets:
            os.environ[key] = str(st.secrets[key])
except Exception:
    pass


@st.cache_resource
def engine():
    return get_engine()


@st.cache_data(ttl=600, show_spinner=False)
def query(sql, params=None):
    """Run a parameterized query, trying twice (a sleeping hosted DB needs a moment)."""
    last_error = None
    for attempt in range(2):
        try:
            with engine().connect() as conn:
                return pd.read_sql(text(sql), conn, params=params or {})
        except Exception as e:
            last_error = e
            engine.clear()
            time.sleep(3)
    raise last_error


def need_data(fetch):
    """Call fetch(); on a connection problem show a short message and stop the page."""
    try:
        return fetch()
    except Exception:
        st.error("Could not reach the database. Check that it is running and that the "
                 "settings in .env (or the app secrets) are right, then reload the page.")
        st.stop()


def sidebar_filters():
    """Date, borough and complaint type filters. Returns (where_sql, params)."""
    bounds = need_data(lambda: query(
        "select min(created_date)::date as lo, max(created_date)::date as hi from service_requests"))
    lo, hi = bounds.loc[0, "lo"], bounds.loc[0, "hi"]
    boroughs = need_data(lambda: query(
        "select distinct borough from service_requests where borough is not null order by 1"))["borough"].tolist()
    types = need_data(lambda: query(
        "select complaint_type from service_requests group by 1 order by count(*) desc"))["complaint_type"].tolist()

    st.sidebar.header("Filters")
    dates = st.sidebar.date_input("Created between", value=(lo, hi), min_value=lo, max_value=hi, key="dates")
    chosen_boroughs = st.sidebar.multiselect("Borough", boroughs, key="boroughs", placeholder="All boroughs")
    chosen_types = st.sidebar.multiselect("Complaint type", types, key="types", placeholder="All complaint types")
    st.sidebar.caption("Leave a box empty to include everything.")

    # date_input returns one date while the user is still picking the second
    if isinstance(dates, tuple) and len(dates) == 2:
        start, end = dates
    else:
        start = end = dates[0] if isinstance(dates, tuple) and dates else dates

    where = "created_date >= :start and created_date < :end"
    params = {"start": start, "end": end + timedelta(days=1)}
    if chosen_boroughs:
        where += " and borough = any(:boroughs)"
        params["boroughs"] = chosen_boroughs
    if chosen_types:
        where += " and complaint_type = any(:types)"
        params["types"] = chosen_types
    return where, params


def kpis(where, params):
    sql = f"""
        select count(distinct unique_key)                                   as total,
               count(*)                                                     as rows_n,
               coalesce(sum(is_closed::int), 0)                             as closed_n,
               count(resolution_hours)                                      as valid_n,
               count(*) filter (where resolution_hours > {THRESHOLD_HOURS}) as over_n,
               percentile_cont(0.5) within group (order by resolution_hours) as median_hours
        from service_requests where {where}"""
    return need_data(lambda: query(sql, params)).iloc[0]


def empty_state(total):
    if total == 0:
        st.info("No requests match these filters. Widen the date range or clear the borough / complaint type boxes.")
        st.stop()


def page_header(title, blurb):
    st.title(title)
    st.write(blurb)
