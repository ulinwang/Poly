-- Database health check for the polymetl.markets table.
-- Run with: clickhouse client --multiquery < scripts/sql/00_database_health.sql
--
-- Verifies row counts, dedup, and presence of expected tables.

SELECT 'tables' AS check, name FROM system.tables WHERE database = 'polymetl';

SELECT
    'markets' AS check,
    count()                                         AS physical_rows,
    uniqExact(market_id)                            AS unique_markets,
    uniqExactIf(market_id, `closed` = 1)            AS unique_closed,
    uniqExactIf(market_id, `closed` = 0)            AS unique_active,
    countIf(volume > 0)                             AS rows_with_volume,
    round(sumIf(volume, `closed` = 1) / 1e9, 3)     AS closed_volume_B_USD,
    round(sumIf(volume, `closed` = 0) / 1e9, 3)     AS active_volume_B_USD,
    min(fetched_at)                                 AS earliest_fetch,
    max(fetched_at)                                 AS latest_fetch
FROM polymetl.markets
FORMAT Vertical;
