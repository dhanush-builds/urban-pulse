import pandas as pd
import plotly.express as px
import streamlit as st

from common import BLUE, RUST, empty_state, kpis, page_header, query, sidebar_filters

st.set_page_config(page_title="Resolution time", layout="wide")
page_header("Resolution time",
            "How long recorded closure took, in hours from created to closed (analyst tasks 8 to 12). "
            "Only requests with a valid closed date are counted.")

where, params = sidebar_filters()
empty_state(kpis(where, params)["total"])

hours_table = query(
    f"select resolution_hours from service_requests where {where} and resolution_hours is not null", params)
hours = hours_table["resolution_hours"]
if hours.empty:
    st.info("None of the selected requests has a valid resolution time.")
    st.stop()

q1 = hours.quantile(0.25)
med = hours.quantile(0.5)
q3 = hours.quantile(0.75)
iqr = q3 - q1
high_fence = q3 + 1.5 * iqr

st.subheader("Descriptive statistics")
mode_h = hours.round(0).mode().iloc[0]
table = pd.DataFrame({
    "statistic": ["n", "mean", "median", "mode (whole hours)", "min", "max", "Q1", "Q3", "IQR", "std deviation", "skewness"],
    "value": [f"{len(hours):,}", f"{hours.mean():,.1f}", f"{med:,.1f}", f"{mode_h:,.0f}", f"{hours.min():,.2f}",
              f"{hours.max():,.1f}", f"{q1:,.2f}", f"{q3:,.2f}", f"{iqr:,.2f}", f"{hours.std():,.1f}",
              f"{hours.skew():.2f}"],
})
left, right = st.columns([1, 2])
left.dataframe(table, hide_index=True, width="stretch", height=(len(table) + 1) * 35 + 3)
right.write(f"The mean ({hours.mean():,.0f} h) sits far above the median ({med:,.1f} h). "
            "A small number of very long cases pull the mean up, so the median is the better "
            "description of a typical request.")

st.subheader("Distribution")
slider_max = int(max(hours.quantile(0.99), high_fence, 48))
cap = st.slider("Show values up to (hours)", 24, slider_max, int(max(24, min(high_fence, slider_max))),
                help="The tail is very long (the slider stops near the 99th percentile); cap the axis to see the bulk of the data.")
fig = px.histogram(hours[hours <= cap], nbins=60, color_discrete_sequence=[BLUE])
fig.update_layout(xaxis_title="resolution hours", yaxis_title="requests", showlegend=False, margin=dict(t=10))
st.plotly_chart(fig, width="stretch")
st.caption(f"{(hours > cap).sum():,} requests above {cap:,} h are not shown in this chart.")

st.subheader("Median resolution by complaint type and agency")
min_n = st.number_input("Minimum valid cases per group", 20, 2000, 100, step=20)


def slowest_chart(box, col, title):
    sql = (f"select {col} as label, count(resolution_hours) as n, "
           f"percentile_cont(0.5) within group (order by resolution_hours) as median_hours "
           f"from service_requests where {where} and resolution_hours is not null "
           f"group by 1 having count(resolution_hours) >= :min_n order by 3 desc limit 15")
    group_params = params.copy()
    group_params["min_n"] = int(min_n)
    df = query(sql, group_params)
    with box:
        st.markdown(f"**Slowest 15 by {title}**")
        if df.empty:
            st.write("No group has enough cases. Lower the minimum.")
        else:
            # reversed, so the slowest bar is drawn at the top
            df = df.sort_index(ascending=False)
            fig = px.bar(df, x="median_hours", y="label", orientation="h",
                         hover_data=["n"], color_discrete_sequence=[BLUE], log_x=True)
            fig.update_layout(xaxis_title="median hours (log scale)", yaxis_title=None, margin=dict(t=10))
            st.plotly_chart(fig, width="stretch")


left, right = st.columns(2)
slowest_chart(left, "complaint_type", "complaint type")
slowest_chart(right, "agency", "agency")

st.subheader("IQR outlier screen")
n_out = int((hours > high_fence).sum())
st.write(f"Upper fence = Q3 + 1.5 x IQR = **{high_fence:,.1f} h**. "
         f"{n_out:,} requests ({100 * n_out / len(hours):.1f}% of valid durations) are above it. "
         "The lower fence is below zero, so nothing can fall under it. "
         "These are cases to look at, not rows to throw away: building repairs and tree work can take months.")
fence_params = params.copy()
fence_params["fence"] = float(high_fence)
by_agency = query(
    f"select agency, count(*) as valid_cases, count(*) filter (where resolution_hours > :fence) as above_fence "
    f"from service_requests where {where} and resolution_hours is not null "
    f"group by 1 having count(*) >= 50 order by 3 desc", fence_params)
if not by_agency.empty:
    by_agency["pct_above_fence"] = (100 * by_agency["above_fence"] / by_agency["valid_cases"]).round(1)
    fig = px.bar(by_agency, x="agency", y="pct_above_fence", hover_data=["valid_cases", "above_fence"],
                 color_discrete_sequence=[RUST])
    fig.update_layout(xaxis_title=None, yaxis_title="% of the agency's cases above the fence", margin=dict(t=10))
    st.plotly_chart(fig, width="stretch")

st.subheader("Time bands")
bands = pd.cut(hours, [-0.001, 1, 24, 72, 168, 720, float("inf")],
               labels=["up to 1 h", "1 to 24 h", "1 to 3 days", "3 to 7 days", "7 to 30 days", "over 30 days"])
band_counts = bands.value_counts().sort_index().rename_axis("band").reset_index(name="requests")
fig = px.bar(band_counts, x="band", y="requests", color_discrete_sequence=[BLUE])
fig.update_layout(xaxis_title=None, margin=dict(t=10))
st.plotly_chart(fig, width="stretch")
