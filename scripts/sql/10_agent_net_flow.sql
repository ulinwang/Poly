-- Per-agent net-flow ratio for the most recent simulation.
-- Apex Predator (high R) absorbs capital as a maker; Prey (low R)
-- pays it out as a taker. Excludes environmental agent_id < 0.
--
-- Run with: clickhouse client < scripts/sql/10_agent_net_flow.sql

WITH most_recent AS (
    SELECT sim_id FROM polymetl.agent_simulations
    ORDER BY started_at DESC LIMIT 1
),
edges_in AS (
    SELECT f.maker_agent_id AS agent_id, sum(f.notional) AS s_in
    FROM polymetl.agent_fills f
    JOIN most_recent m USING (sim_id)
    WHERE f.maker_agent_id >= 0 AND f.taker_agent_id >= 0
    GROUP BY f.maker_agent_id
),
edges_out AS (
    SELECT f.taker_agent_id AS agent_id, sum(f.notional) AS s_out
    FROM polymetl.agent_fills f
    JOIN most_recent m USING (sim_id)
    WHERE f.maker_agent_id >= 0 AND f.taker_agent_id >= 0
    GROUP BY f.taker_agent_id
)
SELECT
    coalesce(i.agent_id, o.agent_id)        AS agent_id,
    coalesce(i.s_in, 0)                     AS s_in,
    coalesce(o.s_out, 0)                    AS s_out,
    coalesce(i.s_in, 0) - coalesce(o.s_out, 0) AS net_flow,
    round(coalesce(i.s_in, 0) / greatest(coalesce(o.s_out, 0), 1e-9), 3) AS ratio_R
FROM edges_in i
FULL OUTER JOIN edges_out o ON i.agent_id = o.agent_id
ORDER BY ratio_R DESC
FORMAT PrettyCompact;
