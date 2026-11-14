"""Descriptive statistics, skewness and IQR outlier screen for resolution_hours.

Reads  data/clean/nyc311_clean.csv
Writes docs/stats_report.md, docs/stats_summary.json, docs/figures/*.png
"""
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

q1, q2, q3 = hours.quantile([0.25, 0.5, 0.75])
iqr = q3 - q1
low_fence, high_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
n_high = int((hours > high_fence).sum())
n_low = int((hours < low_fence).sum())

summary = {
    "n_valid": len(hours),
    "mean": hours.mean(),
    "median": q2,
    "mode": hours.round(0).mode().iloc[0],      # rounded to whole hours, raw values rarely repeat
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
summary = {k: (round(float(v), 3) if not isinstance(v, int) else v) for k, v in summary.items()}
Path("docs/stats_summary.json").write_text(json.dumps(summary, indent=2))

# the fence is negative here, so no low outliers are possible
print(summary)

# ---- charts ----
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
plt.xscale("symlog")
plt.xlabel("resolution hours (symlog axis)")
plt.title("Boxplot of resolution hours")
plt.tight_layout()
plt.savefig(fig_dir / "resolution_boxplot.png", dpi=130)
plt.close()

top_agencies = df["agency"].value_counts().head(8).index
sub = df[df["agency"].isin(top_agencies) & df["resolution_hours"].notna()]
order = sub.groupby("agency")["resolution_hours"].median().sort_values().index
plt.figure(figsize=(9, 4.5))
plt.boxplot([sub.loc[sub["agency"] == a, "resolution_hours"] for a in order],
            tick_labels=list(order), showfliers=False)
plt.ylabel("resolution hours (outliers hidden)")
plt.title("Resolution time by agency (8 busiest)")
plt.tight_layout()
plt.savefig(fig_dir / "resolution_boxplot_by_agency.png", dpi=130)
plt.close()

# ---- other numeric columns ----
other = df[["latitude", "longitude", "created_hour"]].describe().round(4)

# ---- report ----
s = summary
skew_word = "strongly right-skewed" if s["skewness"] > 1 else "moderately skewed" if s["skewness"] > 0.5 else "roughly symmetric"
lines = f"""# Statistical check: resolution_hours

Valid resolution durations: **{s['n_valid']:,}** (closed requests where the closed date is not before the created date).

## Central tendency and spread

| Statistic | Hours |
|---|---|
| Mean | {s['mean']:,.2f} |
| Median | {s['median']:,.2f} |
| Mode (whole hours) | {s['mode']:,.0f} |
| Minimum | {s['min']:,.2f} |
| Maximum | {s['max']:,.1f} |
| Range | {s['range']:,.1f} |
| Q1 / Q3 | {s['q1']:,.2f} / {s['q3']:,.2f} |
| IQR | {s['iqr']:,.2f} |
| Variance | {s['variance']:,.0f} |
| Standard deviation | {s['std']:,.1f} |
| 90th / 95th / 99th percentile | {s['p90']:,.1f} / {s['p95']:,.1f} / {s['p99']:,.1f} |

## Shape

Skewness is **{s['skewness']:.2f}** and excess kurtosis is **{s['kurtosis']:.1f}**, so the distribution is {skew_word} with a very heavy tail.
The mean ({s['mean']:,.1f} h) is far above the median ({s['median']:,.1f} h): a few very long cases pull the mean up, so the median is the fairer "typical" value.

## IQR outlier screen

- Lower fence: Q1 - 1.5 x IQR = {s['low_fence']:,.2f} h (below zero, so no value can fall under it)
- Upper fence: Q3 + 1.5 x IQR = {s['high_fence']:,.2f} h
- Above the upper fence: **{s['n_above_high_fence']:,}** requests ({s['pct_above_high_fence']:.1f}% of valid durations)

These are flags for a closer look, not rows to delete. Long cases such as building repairs or tree work can be real.
Share of valid durations over the project's 72-hour line: {s['share_over_72h']:.1f}%.

## Other numeric fields

{other.to_markdown()}

## Charts

![hist](figures/resolution_hist.png)
![hist log](figures/resolution_hist_log.png)
![box](figures/resolution_boxplot.png)
![box by agency](figures/resolution_boxplot_by_agency.png)
"""
Path("docs/stats_report.md").write_text(lines)
print("wrote docs/stats_report.md")
