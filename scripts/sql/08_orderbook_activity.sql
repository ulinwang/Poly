-- Order-book activity timeline for the most recent simulation:
-- per-tick counts of order types and number of fills.
--
-- Useful for seeing how the book "comes alive" over time and which
-- ticks had the most matching activity.
--
-- Run with: clickhouse client < scripts/sql/08_orderbook_activity.sql

WITH most_recent AS (
    SELECT sim_id FROM polymetl.agent_simulations
    ORDER BY started_at DESC LIMIT 1
)
SELECT
    a.tick,
    countIf(a.order_type = 'LIMIT')   AS limits,
    countIf(a.order_type = 'MARKET')  AS markets,
    countIf(a.order_type = 'CANCEL')  AS cancels,
    countIf(a.order_type = 'HOLD')    AS holds,
    sum(a.n_fills)                    AS total_fills,
    round(avg(a.yes_mid_after), 3)    AS avg_yes_mid_after_tick,
    round(avg(a.api_latency_ms))      AS avg_latency_ms,
    countIf(a.api_error != '')        AS errors
FROM polymetl.agent_actions a
JOIN most_recent m USING (sim_id)
GROUP BY tick
ORDER BY tick
FORMAT PrettyCompact;
