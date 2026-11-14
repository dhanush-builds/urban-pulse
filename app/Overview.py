import plotly.express as px
import streamlit as st

from common import BLUE, THRESHOLD_HOURS, empty_state, kpis, need_data, page_header, query, sidebar_filters

st.set_page_config(page_title="Urban Pulse", layout="wide")

page_header("Urban Pulse",
            "NYC 311 service requests, January to June 2025 (a systematic sample of about 105,000 requests). "
            "Use the filters on the left; every page follows them.")

where, params = sidebar_filters()
k = kpis(where, params)
empty_state(k["total"])

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total requests", f"{int(k['total']):,}",
          help="Distinct unique_key values in the filtered data.")
c2.metric("Recorded closure", f"{100 * k['closed_n'] / k['rows_n']:.1f}%",
          help="Share of filtered rows that have a closed date. It says nothing about citizen satisfaction.")
c3.metric("Open requests", f"{int(k['rows_n'] - k['closed_n']):,}",
          help="Filtered rows with no closed date, as of the extraction date.")
if k["valid_n"] > 0:
    c4.metric("Median resolution", f"{k['median_hours']:.1f} h",
              help="Median hours from created to closed, valid durations only "
                   f"({int(k['valid_n']):,} rows).")
    c5.metric(f"Over {THRESHOLD_HOURS} hours", f"{100 * k['over_n'] / k['valid_n']:.1f}%",
              help=f"Share of valid durations above {THRESHOLD_HOURS} h. The 72-hour line is this "
                   "project's own cut-off, not an official service standard.")
else:
    c4.metric("Median resolution", "n/a")
    c5.metric(f"Over {THRESHOLD_HOURS} hours", "n/a")

st.subheader("Requests per month")
monthly = need_data(lambda: query(
    f"select created_year_month as month, count(*) as requests from service_requests "
    f"where {where} group by 1 order by 1", params))
fig = px.bar(monthly, x="month", y="requests", color_discrete_sequence=[BLUE])
fig.update_layout(xaxis_title=None, yaxis_title="requests", margin=dict(t=10))
st.plotly_chart(fig, width="stretch")

st.subheader("Record preview")
preview = need_data(lambda: query(
    f"select unique_key, created_date, closed_date, agency, complaint_type, borough, status, resolution_hours "
    f"from service_requests where {where} order by created_date desc limit 200", params))
st.caption("The 200 most recent matching requests.")
st.dataframe(preview, hide_index=True, width="stretch")
st.download_button("Download this preview (CSV)", preview.to_csv(index=False), "urban_pulse_preview.csv", "text/csv")

st.caption("Reported requests only, not the full picture of city problems. Status and closed dates are as of "
           "the extraction date. Agencies handle different kinds of work, so comparisons are not rankings.")
