-- ROI per role from serd_results (persisted by src/sim/serd.py).
-- Compares SERD vs DBSCAN_KMEANS baseline side by side, paper Table 7 style.
--
-- Run with: clickhouse client < scripts/sql/12_serd_roi_by_role.sql

WITH most_recent AS (
    SELECT sim_id FROM polymetl.agent_simulations
    ORDER BY started_at DESC LIMIT 1
)
SELECT
    s.method,
    s.role,
    s.n_agents,
    round(s.mean_roi, 4)  AS mean_roi,
    round(s.vol_share, 3) AS vol_share
FROM polymetl.serd_results s FINAL
JOIN most_recent m USING (sim_id)
ORDER BY method, role
FORMAT PrettyCompact;
