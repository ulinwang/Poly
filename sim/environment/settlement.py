"""Market resolution payouts.

Once the market resolves, every YES share is worth $1 (if winning_idx
== 0) or $0; NO shares are worth the complement. Settlement returns
`{agent_id: pnl}` where pnl = final_value − capital_initial.
"""
from __future__ import annotations


def settle(sim) -> dict[int, float]:
    """Compute per-agent PnL once the market closes. Returns empty
    dict if `sim.market_resolved_yes` is None (market still open or
    unknown resolution)."""
    if sim.market_resolved_yes is None:
        return {}
    yes_payoff = 1.0 if sim.market_resolved_yes == 1 else 0.0
    no_payoff = 1.0 - yes_payoff
    pnl: dict[int, float] = {}
    for agent in sim.agents:
        final_value = (
            agent.cash
            + agent.yes_shares * yes_payoff
            + agent.no_shares * no_payoff
        )
        pnl[agent.agent_id] = final_value - agent.persona.capital_initial
    return pnl
