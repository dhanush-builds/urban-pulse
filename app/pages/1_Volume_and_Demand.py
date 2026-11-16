import plotly.express as px
import streamlit as st

from common import BLUE, empty_state, kpis, page_header, query, sidebar_filters

st.set_page_config(page_title="Volume and demand", layout="wide")
page_header("Volume and demand", "What people report, to whom, where and when (analyst tasks 1 to 7).")

where, params = sidebar_filters()
empty_state(kpis(where, params)["total"])


def grouped(col, limit=None):
    sql = "select " + col + " as label, count(*) as requests from service_requests"
    sql = sql + " where " + where + " group by 1 order by 2 desc"
    if limit:
        sql = sql + " limit " + str(limit)
    return query(sql, params)


def bars(df, horizontal=True, height=None):
    if horizontal:
        df = df.sort_index(ascending=False)
        fig = px.bar(df, x="requests", y="label", orientation="h", color_discrete_sequence=[BLUE])
    else:
        fig = px.bar(df, x="label", y="requests", color_discrete_sequence=[BLUE])
    fig.update_layout(xaxis_title=None, yaxis_title=None, margin=dict(t=10), height=height)
    return fig


left, right = st.columns(2)
with left:
    st.subheader("Top 10 complaint types")
    st.plotly_chart(bars(grouped("complaint_type", 10)), width="stretch")
with right:
    st.subheader("Agency workload")
    agencies = grouped("agency")
    st.plotly_chart(bars(agencies.head(10)), width="stretch")
    st.caption(f"{len(agencies)} agencies in this selection, showing the 10 busiest.")

left, right = st.columns(2)
with left:
    st.subheader("Requests by borough")
    st.plotly_chart(bars(grouped("borough"), horizontal=False), width="stretch")
with right:
    st.subheader("Recorded status")
    status = grouped("status")
    status = status.rename(columns={"label": "status"})
    status["share"] = (100 * status["requests"] / status["requests"].sum()).round(2)
    st.dataframe(status, hide_index=True, width="stretch")

st.subheader("Monthly trend")
sql = "select created_year_month as month, count(*) as requests from service_requests"
sql = sql + " where " + where + " group by 1 order by 1"
monthly = query(sql, params)
fig = px.line(monthly, x="month", y="requests", markers=True, color_discrete_sequence=[BLUE])
fig.update_layout(xaxis_title=None, margin=dict(t=10))
fig.update_yaxes(rangemode="tozero")
st.plotly_chart(fig, width="stretch")

st.subheader("Demand by weekday and hour")
sql = "select created_weekday as weekday, created_hour as hour, count(*) as requests"
sql = sql + " from service_requests where " + where + " group by 1, 2 order by 2"
by_hour = query(sql, params)
order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
fig = px.line(by_hour, x="hour", y="requests", color="weekday", category_orders={"weekday": order})
fig.update_layout(xaxis_title="hour of day", margin=dict(t=10))
st.plotly_chart(fig, width="stretch")
