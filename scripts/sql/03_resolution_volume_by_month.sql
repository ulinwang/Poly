-- Monthly breakdown of resolved-market volume.
-- Useful for spotting periods of high prediction-market activity
-- (e.g. the run-up to the 2024 US election).
--
-- Run with: clickhouse client < scripts/sql/03_resolution_volume_by_month.sql

SELECT
    toStartOfMonth(end_date)        AS month,
    count()                         AS markets_resolved,
    round(sum(volume) / 1e6, 2)     AS volume_M_USD,
    round(avg(volume), 0)           AS avg_volume_USD
FROM polymetl.markets FINAL
WHERE `closed` = 1 AND end_date IS NOT NULL
GROUP BY month
ORDER BY month DESC
LIMIT 36
FORMAT PrettyCompact;
