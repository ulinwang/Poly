"""Default observer: best bid/ask + mid + 3-tick yes-mid history.

Information given to the agent: only public top-of-book quotes for
both YES and NO, plus its own portfolio. NO trade tape, NO full
order book, NO other agents' positions. This is the SERD-friendly
default — every agent sees the same public market state, so any
behavioral divergence is downstream of persona + private signal.
"""
from __future__ import annotations

from agent.decision.types import AgentSnapshot, MarketSnapshot


def observe(sim, agent_id: int) -> tuple[MarketSnapshot, AgentSnapshot]:
    """Quote-only observation. `sim` is the env's Simulation object."""
    agent = next((a for a in sim.agents if a.agent_id == agent_id), None)
    if agent is None:
        raise KeyError(f"unknown agent_id {agent_id}")

    market = MarketSnapshot(
        yes_best_bid=sim.book_yes.best_bid(),
        yes_best_ask=sim.book_yes.best_ask(),
        yes_mid=sim.yes_mid,
        no_best_bid=sim.book_no.best_bid(),
        no_best_ask=sim.book_no.best_ask(),
        no_mid=sim.no_mid,
        yes_mid_history=list(sim.yes_mid_history),
        ticks_remaining=getattr(sim, "_ticks_remaining", sim.n_ticks),
        total_ticks=sim.n_ticks,
    )

    n_resting = sum(
        1 for o in (sim.book_yes.bids + sim.book_yes.asks
                    + sim.book_no.bids + sim.book_no.asks)
        if o.agent_id == agent_id
    )
    state = AgentSnapshot(
        agent_id=agent.agent_id, cash=agent.cash,
        yes_shares=agent.yes_shares, no_shares=agent.no_shares,
        n_resting_orders=n_resting,
        private_signal_mu=agent.private_signal_mu,
        private_signal_sigma=agent.private_signal_sigma,
    )
    return market, state
