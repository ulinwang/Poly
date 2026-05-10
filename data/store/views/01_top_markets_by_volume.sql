-- Top 20 markets by lifetime trading volume (across active and closed).
-- Run with: clickhouse client < scripts/sql/01_top_markets_by_volume.sql

SELECT
    slug,
    left(question, 70)        AS question,
    round(volume, 0)          AS volume_usd,
    outcome_prices,
    `closed`                  AS is_closed,
    end_date
FROM polymetl.markets FINAL
ORDER BY volume DESC
LIMIT 20
FORMAT PrettyCompact;
