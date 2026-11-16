SELECT COUNT(DISTINCT unique_key) AS total_requests
FROM service_requests;

SELECT complaint_type, COUNT(*) AS requests,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM service_requests
GROUP BY complaint_type
ORDER BY requests DESC
LIMIT 10;

SELECT agency, COUNT(*) AS requests,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM service_requests
GROUP BY agency
ORDER BY requests DESC;

SELECT borough, COUNT(*) AS requests,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM service_requests
GROUP BY borough
ORDER BY requests DESC;

SELECT created_year_month AS month, COUNT(*) AS requests
FROM service_requests
GROUP BY created_year_month
ORDER BY month;

SELECT created_weekday_num, created_weekday, created_hour, COUNT(*) AS requests
FROM service_requests
GROUP BY created_weekday_num, created_weekday, created_hour
ORDER BY created_weekday_num, created_hour;

SELECT status, COUNT(*) AS requests,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM service_requests
GROUP BY status
ORDER BY requests DESC;

SELECT COUNT(resolution_hours)                                           AS n,
       ROUND(AVG(resolution_hours)::numeric, 2)                          AS mean,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_hours))::numeric, 2) AS median,
       ROUND((MODE() WITHIN GROUP (ORDER BY ROUND(resolution_hours::numeric, 0)))::numeric, 0) AS mode_whole_hours,
       ROUND(MIN(resolution_hours)::numeric, 2)                          AS min,
       ROUND(MAX(resolution_hours)::numeric, 1)                          AS max,
       ROUND((PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY resolution_hours))::numeric, 2) AS q1,
       ROUND((PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY resolution_hours))::numeric, 2) AS q3,
       ROUND(STDDEV_SAMP(resolution_hours)::numeric, 1)                  AS std_dev,
       ROUND(VAR_SAMP(resolution_hours)::numeric, 0)                     AS variance
FROM service_requests
WHERE resolution_hours IS NOT NULL;

SELECT complaint_type, COUNT(resolution_hours) AS n,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_hours))::numeric, 1) AS median_hours
FROM service_requests
WHERE resolution_hours IS NOT NULL
GROUP BY complaint_type
HAVING COUNT(resolution_hours) >= 100
ORDER BY median_hours DESC;

SELECT agency, COUNT(resolution_hours) AS n,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_hours))::numeric, 1) AS median_hours
FROM service_requests
WHERE resolution_hours IS NOT NULL
GROUP BY agency
HAVING COUNT(resolution_hours) >= 100
ORDER BY median_hours DESC;

WITH q AS (
    SELECT PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY resolution_hours) AS q1,
           PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY resolution_hours) AS q3
    FROM service_requests
    WHERE resolution_hours IS NOT NULL
), fence AS (
    SELECT q1, q3, q3 - q1 AS iqr, q1 - 1.5 * (q3 - q1) AS low, q3 + 1.5 * (q3 - q1) AS high
    FROM q
)
SELECT s.agency,
       COUNT(*)                                                           AS valid_cases,
       COUNT(*) FILTER (WHERE s.resolution_hours > f.high)                AS above_high_fence,
       ROUND(100.0 * COUNT(*) FILTER (WHERE s.resolution_hours > f.high) / COUNT(*), 1) AS pct_outlier,
       ROUND(f.high::numeric, 1)                                          AS high_fence
FROM service_requests s CROSS JOIN fence f
WHERE s.resolution_hours IS NOT NULL
GROUP BY s.agency, f.high
HAVING COUNT(*) >= 100
ORDER BY above_high_fence DESC;

SELECT ROUND((
           AVG(POWER(resolution_hours - (SELECT AVG(resolution_hours) FROM service_requests), 3))
           / POWER((SELECT STDDEV_POP(resolution_hours) FROM service_requests), 3)
       )::numeric, 2) AS skewness
FROM service_requests
WHERE resolution_hours IS NOT NULL;

SELECT CASE
           WHEN resolution_hours <= 1   THEN '1  up to 1 h'
           WHEN resolution_hours <= 24  THEN '2  1-24 h'
           WHEN resolution_hours <= 72  THEN '3  1-3 days'
           WHEN resolution_hours <= 168 THEN '4  3-7 days'
           WHEN resolution_hours <= 720 THEN '5  7-30 days'
           ELSE                              '6  over 30 days'
       END AS band,
       COUNT(*) AS requests,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM service_requests
WHERE resolution_hours IS NOT NULL
GROUP BY band
ORDER BY band;

SELECT borough, COUNT(*) AS requests,
       COUNT(latitude) AS with_coordinates,
       ROUND(100.0 * COUNT(latitude) / COUNT(*), 1) AS pct_with_coordinates
FROM service_requests
GROUP BY borough
ORDER BY requests DESC;

SELECT ROUND(latitude::numeric, 2) AS lat_cell, ROUND(longitude::numeric, 2) AS lon_cell,
       COUNT(*) AS requests
FROM service_requests
WHERE NOT flag_missing_coords AND NOT flag_coords_outside_nyc AND NOT flag_repeated_coords
GROUP BY lat_cell, lon_cell
ORDER BY requests DESC
LIMIT 15;

SELECT 'agency' AS grouping, agency AS name, COUNT(*) AS requests,
       ROUND(100.0 * SUM(is_closed::int) / COUNT(*), 1) AS closure_pct
FROM service_requests
GROUP BY agency
HAVING COUNT(*) >= 100
UNION ALL
SELECT 'borough', borough, COUNT(*), ROUND(100.0 * SUM(is_closed::int) / COUNT(*), 1)
FROM service_requests
GROUP BY borough
ORDER BY grouping, closure_pct;

WITH cat AS (
    SELECT complaint_type, COUNT(*) AS requests,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_hours) AS median_hours
    FROM service_requests
    WHERE resolution_hours IS NOT NULL
    GROUP BY complaint_type
    HAVING COUNT(*) >= 100
), cut AS (
    SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY requests)     AS vol_cut,
           PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY median_hours) AS dur_cut
    FROM cat
)
SELECT c.complaint_type, c.requests, ROUND(c.median_hours::numeric, 1) AS median_hours
FROM cat c CROSS JOIN cut
WHERE c.requests >= cut.vol_cut AND c.median_hours >= cut.dur_cut
ORDER BY c.requests DESC;
