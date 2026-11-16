import plotly.express as px
import streamlit as st

from common import BLUE, THRESHOLD_HOURS, empty_state, kpis, page_header, query, sidebar_filters

st.set_page_config(page_title="Urban Pulse", layout="wide")

page_header("Urban Pulse",
            "NYC 311 requests from January to June 2025, a sample of about 105,000. "
            "The filters on the left work on every page.")

where, params = sidebar_filters()
k = kpis(where, params)
empty_state(k["total"])

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total requests", f"{int(k['total']):,}",
          help="Number of different request ids after the filters.")
c2.metric("Recorded closure", f"{100 * k['closed_n'] / k['rows_n']:.1f}%",
          help="Share of requests that have a closed date.")
c3.metric("Open requests", f"{int(k['rows_n'] - k['closed_n']):,}",
          help="Requests with no closed date.")
if k["valid_n"] > 0:
    c4.metric("Median resolution", f"{k['median_hours']:.1f} h",
              help=f"Middle time from created to closed, over {int(k['valid_n']):,} requests.")
    c5.metric(f"Over {THRESHOLD_HOURS} hours", f"{100 * k['over_n'] / k['valid_n']:.1f}%",
              help=f"Share of requests that took more than {THRESHOLD_HOURS} hours. The 72 is our own line.")
else:
    c4.metric("Median resolution", "n/a")
    c5.metric(f"Over {THRESHOLD_HOURS} hours", "n/a")

st.subheader("Requests per month")
sql = "select created_year_month as month, count(*) as requests from service_requests"
sql = sql + " where " + where + " group by 1 order by 1"
monthly = query(sql, params)
fig = px.bar(monthly, x="month", y="requests", color_discrete_sequence=[BLUE])
fig.update_layout(xaxis_title=None, yaxis_title="requests", margin=dict(t=10))
st.plotly_chart(fig, width="stretch")

st.subheader("Record preview")
sql = "select unique_key, created_date, closed_date, agency, complaint_type, borough, status, resolution_hours"
sql = sql + " from service_requests where " + where + " order by created_date desc limit 200"
preview = query(sql, params)
st.caption("The 200 most recent matching requests.")
st.dataframe(preview, hide_index=True, width="stretch")
st.download_button("Download this preview (CSV)", preview.to_csv(index=False), "urban_pulse_preview.csv", "text/csv")

st.caption("These are only the problems people reported. Status and closed dates are as of the day I downloaded the data.")
