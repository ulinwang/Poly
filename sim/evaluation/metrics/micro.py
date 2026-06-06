"""Micro (single-agent level) metrics.

`agent_snapshot` / `snapshot_all` run live, once per agent per tick.
`agent_eval` summarizes one agent for a finished run. Operates on the
`AgentRuntime` objects held by the simulation (environment.env), reading only
public attributes (cash, cash_reserved, yes_shares, no_shares, belief, persona).
"""
from __future__ import annotations

from typing import Any, Optional

from evaluation.schema import AgentEval, AgentSnapshot


def _initial_capital(agent: Any) -> float:
    persona = getattr(agent, "persona", None)
    return float(getattr(persona, "capital_initial", 0.0) or 0.0)


def mark_to_market_pnl(agent: Any, yes_mid: float, no_mid: float) -> float:
    """Cash + inventory marked at current mids, minus initial capital."""
    return (
        float(agent.cash)
        + float(agent.yes_shares) * float(yes_mid)
        + float(agent.no_shares) * float(no_mid)
        - _initial_capital(agent)
    )


def agent_snapshot(tick: int, agent: Any, yes_mid: float, no_mid: float) -> AgentSnapshot:
    """One AgentSnapshot for the given agent at the current mids."""
    belief = getattr(agent, "belief", None) or {}
    return AgentSnapshot(
        tick=tick,
        agent_id=int(agent.agent_id),
        persona=str(getattr(agent.persona, "persona_type", "")),
        cash=float(agent.cash),
        cash_reserved=float(getattr(agent, "cash_reserved", 0.0)),
        pos_yes=float(agent.yes_shares),
        pos_no=float(agent.no_shares),
        belief_yes=(float(belief["yes_prob"]) if belief.get("yes_prob") is not None else None),
        belief_conf=(float(belief["confidence"]) if belief.get("confidence") is not None else None),
        pnl=mark_to_market_pnl(agent, yes_mid, no_mid),
    )


def snapshot_all(tick: int, agents: list, yes_mid: float, no_mid: float) -> list[AgentSnapshot]:
    """AgentSnapshot for every agent at the current mids."""
    return [agent_snapshot(tick, a, yes_mid, no_mid) for a in agents]


def agent_eval(
    agent: Any,
    final_pnl: float,
    n_trades: int,
    belief_cal_err: Optional[float] = None,
    role: Optional[str] = None,
) -> AgentEval:
    """Micro scorecard for one agent at the end of a run."""
    return AgentEval(
        agent_id=int(agent.agent_id),
        persona=str(getattr(agent.persona, "persona_type", "")),
        final_pnl=float(final_pnl),
        n_trades=int(n_trades),
        win=(final_pnl > 0) if final_pnl is not None else None,
        belief_cal_err=belief_cal_err,
        role=role,
    )
