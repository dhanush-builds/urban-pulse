import os
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))
from db import get_engine

BLUE = "#1f5f8b"
RUST = "#c8553d"
THRESHOLD_HOURS = 72  # our own cut-off, not an official service standard

# Streamlit Cloud keeps the database settings in st.secrets, locally they come from .env
try:
    for key in ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME", "PGSSLMODE"]:
        if key in st.secrets:
            os.environ[key] = str(st.secrets[key])
except FileNotFoundError:
    pass


engine = get_engine()


def run_query(sql, params):
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def query(sql, params=None):
    if params is None:
        params = {}
    try:
        return run_query(sql, params)
    except SQLAlchemyError:
        st.error("Could not reach the database. Check that it is running and that the "
                 "settings in .env (or the app secrets) are right, then reload the page.")
        st.stop()


def sidebar_filters():
    bounds = query("select min(created_date)::date as lo, max(created_date)::date as hi from service_requests")
    first_day = bounds.loc[0, "lo"]
    last_day = bounds.loc[0, "hi"]

    borough_table = query("select distinct borough from service_requests where borough is not null order by 1")
    boroughs = borough_table["borough"].tolist()

    type_table = query("select complaint_type from service_requests group by 1 order by count(*) desc")
    types = type_table["complaint_type"].tolist()

    st.sidebar.header("Filters")
    dates = st.sidebar.date_input("Created between", value=(first_day, last_day),
                                  min_value=first_day, max_value=last_day, key="dates")
    chosen_boroughs = st.sidebar.multiselect("Borough", boroughs, key="boroughs", placeholder="All boroughs")
    chosen_types = st.sidebar.multiselect("Complaint type", types, key="types", placeholder="All complaint types")
    st.sidebar.caption("Leave a box empty to include everything.")

    # date_input gives one date while the user is still picking the second one
    if isinstance(dates, tuple):
        if len(dates) == 2:
            start = dates[0]
            end = dates[1]
        elif len(dates) == 1:
            start = dates[0]
            end = dates[0]
        else:
            start = first_day
            end = last_day
    else:
        start = dates
        end = dates

    where = "created_date >= :start and created_date < :end"
    params = {"start": start, "end": end + timedelta(days=1)}
    if chosen_boroughs:
        # = any(list) matches any value in the list
        where += " and borough = any(:boroughs)"
        params["boroughs"] = chosen_boroughs
    if chosen_types:
        where += " and complaint_type = any(:types)"
        params["types"] = chosen_types
    return where, params


def kpis(where, params):
    sql = "select count(distinct unique_key) as total, count(*) as rows_n, "
    sql = sql + "coalesce(sum(is_closed::int), 0) as closed_n, "
    sql = sql + "count(resolution_hours) as valid_n, "
    sql = sql + "count(*) filter (where resolution_hours > " + str(THRESHOLD_HOURS) + ") as over_n, "
    sql = sql + "percentile_cont(0.5) within group (order by resolution_hours) as median_hours "
    sql = sql + "from service_requests where " + where
    return query(sql, params).iloc[0]


def empty_state(total):
    if total == 0:
        st.info("No requests match these filters. Widen the date range or clear the borough / complaint type boxes.")
        st.stop()


def page_header(title, blurb):
    st.title(title)
    st.write(blurb)
