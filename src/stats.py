import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats

df = pd.read_csv("data/clean/nyc311_clean.csv", low_memory=False)
hours = df["resolution_hours"].dropna()
fig_dir = Path("docs/figures")
fig_dir.mkdir(parents=True, exist_ok=True)

q1 = hours.quantile(0.25)
q2 = hours.quantile(0.5)
q3 = hours.quantile(0.75)
iqr = q3 - q1
low_fence = q1 - 1.5 * iqr
high_fence = q3 + 1.5 * iqr
n_high = int((hours > high_fence).sum())
n_low = int((hours < low_fence).sum())

summary = {
    "n_valid": len(hours),
    "mean": hours.mean(),
    "median": q2,
    "mode": hours.round(0).mode().iloc[0],
    "min": hours.min(),
    "max": hours.max(),
    "range": hours.max() - hours.min(),
    "q1": q1,
    "q3": q3,
    "iqr": iqr,
    "variance": hours.var(),
    "std": hours.std(),
    "skewness": stats.skew(hours),
    "kurtosis": stats.kurtosis(hours),
    "p90": hours.quantile(0.90),
    "p95": hours.quantile(0.95),
    "p99": hours.quantile(0.99),
    "low_fence": low_fence,
    "high_fence": high_fence,
    "n_above_high_fence": n_high,
    "n_below_low_fence": n_low,
    "pct_above_high_fence": 100 * n_high / len(hours),
    "share_over_72h": 100 * (hours > 72).mean(),
}
rounded = {}
for key in summary:
    value = summary[key]
    if isinstance(value, int):
        rounded[key] = value
    else:
        rounded[key] = round(float(value), 3)
summary = rounded
Path("docs/stats_summary.json").write_text(json.dumps(summary, indent=2))

plt.figure(figsize=(8, 4))
plt.hist(hours[hours <= high_fence], bins=50, color="#3b6ea5")
plt.xlabel("resolution hours (cut at the upper fence)")
plt.ylabel("requests")
plt.title("Resolution time, inside the IQR fences")
plt.tight_layout()
plt.savefig(fig_dir / "resolution_hist.png", dpi=130)
plt.close()

plt.figure(figsize=(8, 4))
plt.hist(hours[hours > 0], bins=60, color="#a5603b", log=True)
plt.xlabel("resolution hours (all valid values > 0)")
plt.ylabel("requests (log scale)")
plt.title("Resolution time, full range")
plt.tight_layout()
plt.savefig(fig_dir / "resolution_hist_log.png", dpi=130)
plt.close()

plt.figure(figsize=(8, 3))
plt.boxplot(hours, orientation="horizontal", showfliers=True, flierprops={"markersize": 2})
plt.xlabel("resolution hours")
plt.title("Boxplot of resolution hours")
plt.tight_layout()
plt.savefig(fig_dir / "resolution_boxplot.png", dpi=130)
plt.close()

top_agencies = df["agency"].value_counts().head(8).index
sub = df[df["agency"].isin(top_agencies) & df["resolution_hours"].notna()]
order = sub.groupby("agency")["resolution_hours"].median().sort_values().index
plt.figure(figsize=(9, 4.5))
agency_names = list(order)
agency_hours = []
for name in agency_names:
    agency_hours.append(sub.loc[sub["agency"] == name, "resolution_hours"])
plt.boxplot(agency_hours, tick_labels=agency_names, showfliers=False)
plt.ylabel("resolution hours (outliers hidden)")
plt.title("Resolution time by agency (8 busiest)")
plt.tight_layout()
plt.savefig(fig_dir / "resolution_boxplot_by_agency.png", dpi=130)
plt.close()
