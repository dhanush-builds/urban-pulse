# Urban Pulse: final report

## 1. What was done

I pulled a sample of NYC 311 service requests from the NYC Open Data API, cleaned it, checked the statistics of the resolution times, loaded it into PostgreSQL, answered the 15 analyst questions in SQL and Python, and built a Streamlit dashboard with five KPIs.

| Step | Script | Output |
|---|---|---|
| Extract | `src/extract.py` | `data/raw/nyc311_raw.csv`, `docs/extraction_log.json` |
| Clean | `src/clean.py` | `data/clean/nyc311_clean.csv`, `docs/cleaning_log.md`, `docs/data_dictionary.md` |
| Statistics | `src/stats.py` | `docs/stats_report.md`, charts in `docs/figures/` |
| Load | `src/load.py` | table `service_requests`, `docs/load_log.json` |
| Analysis | `sql/analysis.sql`, `notebooks/eda.ipynb` | 15 tasks with evidence |
| Dashboard | `app/` | Overview page and four analyst pages |

## 2. Data

- Window: requests created 1 January to 30 June 2025. The API holds about 1.76 million of them.
- Sample: rows whose `unique_key` ends in 12, 29, 37, 58, 64 or 91 (about 6%). Keys are running numbers, so this is unrelated to time, agency or type. Taking the first 100,000 by date would only have covered the first ten days of January.
- Realised size: **105,540 rows**, 25 source fields, no duplicate keys. The brief says about 100,000 and asks for the real count.
- Extracted 14 November 2026. Status and closed dates are as of that day, so a request created in June may have been closed later than a January one had time to be.

### Data quality

Nothing was deleted. Odd rows got a flag (`docs/cleaning_log.md` has the counts):

- 38 requests have a closed date before the created date. They count as closed but have no resolution time.
- 352 requests have status `Closed` but no closed date, and 85 have a closed date but another status. The dashboard follows the brief: closure means a recorded closed date, so those 352 count as open.
- 2,174 requests were closed at the exact second they were created. They look like automatic closures and are kept.
- 150 complaint type values differed only in letter case and were merged to the most common spelling.
- 1,648 rows (1.6%) have no coordinates. `due_date` is empty in 99.6% of rows, so it is not used.
- **One police-station address (655 East 230 Street) carries 2,877 rows, mostly residential noise.** It is a placeholder location, not a hotspot, so the coordinate is flagged and left out of the geographic view.

### Load validation

Raw 105,540 = clean 105,540 = database 105,540. All keys are distinct, the count of valid resolution times matches (104,115), and five random rows match the CSV (`docs/load_log.json`).

## 3. Statistics of resolution time

104,115 requests have a valid duration.

| | Hours |
|---|---|
| Median | 7.8 |
| Mean | 261.8 |
| Q1 / Q3 | 1.13 / 66.9 |
| Standard deviation | 1,008 |
| 95th percentile | 1,427 |
| Maximum | 15,568 |
| Skewness | 6.66 |

The distribution is extremely right-skewed. Most requests close within a day (62%), but a long tail pulls the mean 33 times above the median. The median is the number to quote.

IQR screen: the upper fence is 165.7 hours and 16,547 requests (15.9%) are above it. The lower fence is below zero. These are not errors: building repairs and similar jobs really can take months, and the flag only says where to look. By agency the share above the fence ranges from near 0% for NYPD to 100% for EDC.

## 4. Findings

1. **Volume.** NYPD receives 46% of requests, HPD 22%, DSNY 9%. The ten biggest complaint types cover 58% of the sample, led by Illegal Parking (16%), Residential Noise (12%) and Heat/Hot Water (9%).
2. **Boroughs.** Brooklyn 30%, Queens 24%, Bronx 23%, Manhattan 20%, Staten Island 4%. These are counts, not rates per resident, so they say nothing about which borough has more problems per person.
3. **Time.** January is the busiest month (674 requests per day in the sample against 548 in February), consistent with heating complaints in winter. On weekdays requests peak between 9 and 12 in the morning. On weekends the late evening and midnight hours are busier, which fits the noise complaints.
4. **Status.** 98.9% of requests have status Closed. This is a recorded status, not a quality measure.
5. **Resolution by agency.** NYPD is fastest (median 1.4 hours), HPD takes 77 hours, DOB 266 hours, TLC 1,605 hours and EDC 7,593 hours. The EDC figure is driven entirely by Noise - Helicopter (median 7,593 hours): these complaints seem to follow a very different process from the rest, so the agency comparison should not be read as speed of service.
6. **Closure rate.** DHS (73.7%), EDC (86.7%) and DPR (86.9%) have the lowest rates of a recorded closed date. The five boroughs are all between 98.0% and 99.4%.
7. **High volume and slow.** Unsanitary Condition (3,169 cases, median 282 hours) and Door/Window (1,307 cases, median 305 hours) are in the top quarter for both volume and duration. Both are HPD housing complaints.
8. **Geography.** Requests concentrate in the Bronx and upper Manhattan around the 40.82 to 40.89 N band, with further busy cells in Brooklyn and lower Manhattan. Coordinates are available for 97% or more of requests in every borough except "Unspecified".

## 5. KPI definitions

| KPI | Definition |
|---|---|
| Total requests | distinct `unique_key` in the filtered data |
| Recorded closure | filtered rows with a closed date, divided by filtered rows |
| Open requests | filtered rows with no closed date |
| Median resolution | median `resolution_hours`, valid durations only |
| Over 72 hours | valid durations above 72 hours, divided by valid durations |

The 72-hour line is a project choice and not an official service standard.

## 6. Limitations

- 311 records are reported requests, not the real amount of urban problems. Areas and groups that report more will look busier.
- The sample covers six months of 2025 and is systematic, not random. It was checked to cover every day and hour, but it is still a sample.
- Closed dates are as of 14 November 2026. Recorded closure is not satisfaction and not a verified fix.
- Agencies handle work of very different size and complexity, so agency and category comparisons are not performance rankings.
- Some location data is a placeholder, and 1.6% of rows have none.
- Status and closed date disagree in 437 rows. The dashboard uses the closed date.
- The project was built on PostgreSQL instead of the suggested MySQL.

## 7. What could be done next

- Compare against another half-year to separate seasonal patterns from one-off effects.
- Look at the Noise - Helicopter and DHS closure patterns with the agencies' own process descriptions.
- Normalise borough counts by population before comparing boroughs.
