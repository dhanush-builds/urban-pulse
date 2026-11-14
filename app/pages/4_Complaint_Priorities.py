import plotly.express as px
import streamlit as st

from common import BLUE, RUST, empty_state, kpis, need_data, page_header, query, sidebar_filters

st.set_page_config(page_title="Complaint priorities", layout="wide")
page_header("Complaint priorities",
            "Complaint types that are both frequent and slow to close (analyst task 15). "
            "A type counts as high volume and long when it is in the top quarter for both measures.")

where, params = sidebar_filters()
empty_state(kpis(where, params)["total"])

min_n = st.number_input("Minimum valid cases per complaint type", 20, 1000, 100, step=20)
cats = need_data(lambda: query(
    f"select complaint_type, count(*) as requests, "
    f"percentile_cont(0.5) within group (order by resolution_hours) as median_hours "
    f"from service_requests where {where} and resolution_hours is not null "
    f"group by 1 having count(*) >= :min_n", {**params, "min_n": int(min_n)}))

if len(cats) < 4:
    st.info("Too few complaint types with enough cases to compare. Lower the minimum or widen the filters.")
    st.stop()

vol_cut = cats["requests"].quantile(0.75)
dur_cut = cats["median_hours"].quantile(0.75)
cats["priority"] = (cats["requests"] >= vol_cut) & (cats["median_hours"] >= dur_cut)

fig = px.scatter(cats, x="requests", y="median_hours", log_x=True, log_y=True, hover_name="complaint_type",
                 color="priority", color_discrete_map={True: RUST, False: BLUE})
fig.add_vline(x=vol_cut, line_dash="dot", line_color="gray")
fig.add_hline(y=dur_cut, line_dash="dot", line_color="gray")
fig.update_layout(xaxis_title="requests with a valid duration (log scale)",
                  yaxis_title="median resolution hours (log scale)", legend_title="High volume and long",
                  margin=dict(t=10))
st.plotly_chart(fig, width="stretch")
st.caption(f"Dotted lines are the 75th percentile across complaint types: {vol_cut:,.0f} requests and {dur_cut:,.1f} hours.")

hits = cats[cats["priority"]].sort_values("requests", ascending=False)
st.subheader("High volume and long median")
if hits.empty:
    st.write("No complaint type passes both cut-offs in this selection.")
else:
    st.dataframe(hits[["complaint_type", "requests", "median_hours"]].round(1), hide_index=True, width="stretch")
st.caption("Different complaint types have different case complexity, so a long median does not by itself mean "
           "poor service. Use this list to decide where to look first.")
