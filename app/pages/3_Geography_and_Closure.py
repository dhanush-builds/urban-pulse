import plotly.express as px
import streamlit as st

from common import BLUE, empty_state, kpis, page_header, query, sidebar_filters

st.set_page_config(page_title="Geography and closure", layout="wide")
page_header("Geography and closure",
            "Where requests come from, and how often a closed date is recorded (analyst tasks 13 and 14).")

where, params = sidebar_filters()
empty_state(kpis(where, params)["total"])

st.subheader("Location data coverage by borough")
sql = "select borough, count(*) as requests, count(latitude) as with_coordinates, "
sql = sql + "round(100.0 * count(latitude) / count(*), 1) as pct_with_coordinates "
sql = sql + "from service_requests where " + where + " group by 1 order by 2 desc"
cover = query(sql, params)
st.dataframe(cover, hide_index=True, width="stretch")

st.subheader("Where requests concentrate")
st.caption("Each cell is about 1 km wide (0.01 degrees). Rows with no coordinates, rows outside the city, "
           "and one police station point that holds about 2.7% of all rows are left out.")
sql = "select round(latitude::numeric, 2) || ', ' || round(longitude::numeric, 2) as cell, count(*) as requests "
sql = sql + "from service_requests where " + where
sql = sql + " and not flag_missing_coords and not flag_coords_outside_nyc and not flag_repeated_coords"
sql = sql + " group by 1 order by 2 desc limit 15"
cells = query(sql, params)
if cells.empty:
    st.info("No usable coordinates for this selection.")
else:
    cells = cells.sort_index(ascending=False)
    fig = px.bar(cells, x="requests", y="cell", orientation="h", color_discrete_sequence=[BLUE])
    fig.update_layout(xaxis_title="requests", yaxis_title="cell (latitude, longitude)", margin=dict(t=10))
    st.plotly_chart(fig, width="stretch")

st.subheader("Recorded closure rate")
st.caption("Share of requests that have a closed date.")


def closure_chart(box, col, title):
    sql = "select " + col + " as label, count(*) as requests, "
    sql = sql + "round(100.0 * sum(is_closed::int) / count(*), 1) as closure_pct "
    sql = sql + "from service_requests where " + where
    sql = sql + " group by 1 having count(*) >= 30 order by 3"
    df = query(sql, params)
    with box:
        st.markdown(f"**By {title}** (groups with at least 30 requests)")
        if df.empty:
            st.write("Not enough requests.")
            return
        fig = px.bar(df, x="closure_pct", y="label", orientation="h", hover_data=["requests"],
                     color_discrete_sequence=[BLUE])
        fig.update_layout(xaxis_title="% with a closed date", yaxis_title=None, margin=dict(t=10),
                          xaxis_range=[min(df["closure_pct"].min() - 2, 90), 100.5])
        st.plotly_chart(fig, width="stretch")


left, right = st.columns(2)
closure_chart(left, "agency", "agency")
closure_chart(right, "borough", "borough")
