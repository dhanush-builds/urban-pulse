import plotly.express as px
import streamlit as st

from common import BLUE, RUST, empty_state, kpis, need_data, page_header, query, sidebar_filters

st.set_page_config(page_title="Geography and closure", layout="wide")
page_header("Geography and closure",
            "Where requests come from, and how often a closed date is recorded (analyst tasks 13 and 14).")

where, params = sidebar_filters()
empty_state(kpis(where, params)["total"])

st.subheader("Location data coverage by borough")
cover = need_data(lambda: query(
    f"select borough, count(*) as requests, count(latitude) as with_coordinates, "
    f"round(100.0 * count(latitude) / count(*), 1) as pct_with_coordinates "
    f"from service_requests where {where} group by 1 order by 2 desc", params))
st.dataframe(cover, hide_index=True, width="stretch")

st.subheader("Where requests concentrate")
st.caption("Each cell is about 1 km across (0.01 degrees). Requests without usable coordinates, outside the city box, "
           "or at the one placeholder point (a police station that carries about 2.7% of all rows) are left out.")
cells = need_data(lambda: query(
    f"select round(latitude::numeric, 2) as lat, round(longitude::numeric, 2) as lon, count(*) as requests "
    f"from service_requests where {where} and not flag_missing_coords and not flag_coords_outside_nyc "
    f"and not flag_repeated_coords group by 1, 2", params))
if cells.empty:
    st.info("No usable coordinates for this selection.")
else:
    cells["lat"] = cells["lat"].astype(float)
    cells["lon"] = cells["lon"].astype(float)
    # plain lon/lat scatter instead of a tile map: no WebGL or outside map service needed
    fig = px.scatter(cells, x="lon", y="lat", color="requests", size="requests", size_max=14,
                     color_continuous_scale="Blues", height=600)
    fig.update_yaxes(scaleanchor="x", scaleratio=1.32)   # 1 degree of longitude is shorter than latitude at 40.7 N
    fig.update_layout(margin=dict(t=0, b=0), xaxis_title="longitude", yaxis_title="latitude")
    st.plotly_chart(fig, width="stretch")
    st.markdown("**Busiest cells**")
    st.dataframe(cells.sort_values("requests", ascending=False).head(10), hide_index=True, width="stretch")

st.subheader("Recorded closure rate")
st.caption("Share of requests with a closed date. This is not a measure of satisfaction or of verified resolution.")
left, right = st.columns(2)
for box, col, title in [(left, "agency", "agency"), (right, "borough", "borough")]:
    df = need_data(lambda: query(
        f"select {col} as label, count(*) as requests, "
        f"round(100.0 * sum(is_closed::int) / count(*), 1) as closure_pct "
        f"from service_requests where {where} group by 1 having count(*) >= 30 order by 3", params))
    with box:
        st.markdown(f"**By {title}** (groups with at least 30 requests)")
        if df.empty:
            st.write("Not enough requests.")
            continue
        fig = px.bar(df, x="closure_pct", y="label", orientation="h", hover_data=["requests"],
                     color_discrete_sequence=[BLUE])
        fig.update_layout(xaxis_title="% with a closed date", yaxis_title=None, margin=dict(t=10),
                          xaxis_range=[min(df["closure_pct"].min() - 2, 90), 100.5])
        st.plotly_chart(fig, width="stretch")
