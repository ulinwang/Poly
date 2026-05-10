-- Pool SERD results across multiple simulation runs to gain statistical
-- power that single small-N sims cannot provide. Reports per-role
-- weighted-mean ROI and number of contributing sims per role.
--
-- Run with: clickhouse client < scripts/sql/13_pool_serd_across_sims.sql

SELECT
    method,
    role,
    count()                                              AS n_sims,
    sum(n_agents)                                        AS total_agents,
    round(
        sum(mean_roi * n_agents) / greatest(sum(n_agents), 1),
        4
    )                                                    AS pooled_mean_roi
FROM polymetl.serd_results FINAL
GROUP BY method, role
ORDER BY method, role
FORMAT PrettyCompact;
