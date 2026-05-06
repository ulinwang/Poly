-- Compare simulated mid-price path vs real Polymarket CLOB trade prices
-- for a given simulation. Edit the WHERE clause to pick which sim_id.
--
-- Run with: clickhouse client < scripts/sql/06_sim_vs_real_price_path.sql

-- 1. Simulated YES mid at the end of each tick
WITH most_recent AS (
    SELECT sim_id, market_id, n_ticks
    FROM polymetl.agent_simulations
    ORDER BY started_at DESC
    LIMIT 1
)
SELECT
    'SIM' AS source,
    a.tick AS tick,
    NULL AS trade_time,
    avg(a.yes_mid_after) AS yes_price,
    NULL AS volume_usd
FROM polymetl.agent_actions a
JOIN most_recent m USING (sim_id)
GROUP BY a.tick
ORDER BY tick
FORMAT PrettyCompact;

-- 2. Real Polymarket trades for the same market (if any)
WITH most_recent AS (
    SELECT sim_id, market_id
    FROM polymetl.agent_simulations
    ORDER BY started_at DESC
    LIMIT 1
)
SELECT
    'REAL' AS source,
    NULL AS tick,
    toStartOfHour(t.trade_time) AS trade_hour,
    avg(t.price) AS yes_price,
    sum(t.size * t.price) AS volume_usd
FROM polymetl.market_trade_history t
JOIN most_recent m USING (market_id)
GROUP BY trade_hour
ORDER BY trade_hour
LIMIT 100
FORMAT PrettyCompact;
