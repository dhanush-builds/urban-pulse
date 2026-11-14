import plotly.express as px
import streamlit as st

from common import BLUE, empty_state, kpis, need_data, page_header, query, sidebar_filters

st.set_page_config(page_title="Volume and demand", layout="wide")
page_header("Volume and demand", "What people report, to whom, where and when (analyst tasks 1 to 7).")

where, params = sidebar_filters()
empty_state(kpis(where, params)["total"])


def grouped(col, limit=None):
    sql = (f"select {col} as label, count(*) as requests from service_requests where {where} "
           f"group by 1 order by 2 desc" + (f" limit {limit}" if limit else ""))
    return need_data(lambda: query(sql, params))


def bars(df, horizontal=True, height=None):
    if horizontal:
        fig = px.bar(df.iloc[::-1], x="requests", y="label", orientation="h", color_discrete_sequence=[BLUE])
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
    st.caption(f"{len(agencies)} agencies in this selection, the 10 busiest are shown.")

left, right = st.columns(2)
with left:
    st.subheader("Requests by borough")
    st.plotly_chart(bars(grouped("borough"), horizontal=False), width="stretch")
with right:
    st.subheader("Recorded status")
    status = grouped("status")
    st.dataframe(status.rename(columns={"label": "status"}).assign(
        share=lambda d: (100 * d["requests"] / d["requests"].sum()).round(2)),
        hide_index=True, width="stretch")

st.subheader("Monthly trend")
monthly = need_data(lambda: query(
    f"select created_year_month as month, count(*) as requests from service_requests "
    f"where {where} group by 1 order by 1", params))
fig = px.line(monthly, x="month", y="requests", markers=True, color_discrete_sequence=[BLUE])
fig.update_layout(xaxis_title=None, margin=dict(t=10))
st.plotly_chart(fig, width="stretch")

st.subheader("Demand by weekday and hour")
heat = need_data(lambda: query(
    f"select created_weekday_num as d, created_weekday as weekday, created_hour as hour, count(*) as requests "
    f"from service_requests where {where} group by 1, 2, 3", params))
grid = heat.pivot(index="weekday", columns="hour", values="requests").fillna(0)
order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
grid = grid.reindex([d for d in order if d in grid.index])
fig = px.imshow(grid, aspect="auto", color_continuous_scale="Blues",
                labels=dict(x="hour of day", y="", color="requests"))
fig.update_layout(margin=dict(t=10))
st.plotly_chart(fig, width="stretch")
st.caption("Time is the time the request was created, in New York local time as recorded by the city.")
