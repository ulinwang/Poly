-- Per-persona PnL breakdown for the most recent simulation.
--
-- Final PnL = (cash + yes_shares * yes_payoff + no_shares * no_payoff)
--             - capital_initial
-- where yes_payoff = 1 if market resolved YES else 0, vice versa.
--
-- Run with: clickhouse client < scripts/sql/07_persona_pnl_breakdown.sql

WITH most_recent AS (
    SELECT sim_id, market_resolved_yes, n_ticks
    FROM polymetl.agent_simulations
    ORDER BY started_at DESC
    LIMIT 1
),
final_pos AS (
    SELECT p.sim_id, p.agent_id,
           argMax(p.cash, p.tick)        AS final_cash,
           argMax(p.yes_shares, p.tick)  AS final_yes,
           argMax(p.no_shares, p.tick)   AS final_no
    FROM polymetl.agent_positions p
    JOIN most_recent m USING (sim_id)
    GROUP BY p.sim_id, p.agent_id
)
SELECT
    pers.persona_type                                    AS persona,
    count()                                              AS n_agents,
    round(avg(
        fp.final_cash
        + fp.final_yes * if(m.market_resolved_yes = 1, 1.0, 0.0)
        + fp.final_no  * if(m.market_resolved_yes = 1, 0.0, 1.0)
        - pers.capital_initial
    ), 2)                                                 AS avg_pnl_usd,
    round(min(
        fp.final_cash
        + fp.final_yes * if(m.market_resolved_yes = 1, 1.0, 0.0)
        + fp.final_no  * if(m.market_resolved_yes = 1, 0.0, 1.0)
        - pers.capital_initial
    ), 2)                                                 AS min_pnl_usd,
    round(max(
        fp.final_cash
        + fp.final_yes * if(m.market_resolved_yes = 1, 1.0, 0.0)
        + fp.final_no  * if(m.market_resolved_yes = 1, 0.0, 1.0)
        - pers.capital_initial
    ), 2)                                                 AS max_pnl_usd
FROM polymetl.agent_personas pers
JOIN final_pos fp USING (sim_id, agent_id)
JOIN most_recent m USING (sim_id)
GROUP BY pers.persona_type
ORDER BY avg_pnl_usd DESC
FORMAT PrettyCompact;
