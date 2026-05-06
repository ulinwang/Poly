"""
Multi-agent simulation environment using two CLOBs (one per outcome
token, mirroring real Polymarket). Each tick is a "matching window":
all agents observe state, submit one order, the engine processes them
in randomized order (so no single agent always goes first), and fills
update positions/cash. At end the resolver pays $1 per winning share.

Structure:
  Simulation
    ├─ book_yes : OrderBook    (YES outcome token, prices ∈ [0,1])
    ├─ book_no  : OrderBook    (NO outcome token, prices ∈ [0,1])
    ├─ agents   : list[AgentRuntime]
    └─ logs     : actions/orders/fills/positions
"""
from __future__ import annotations

import datetime as dt
import logging
import random
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .agent import (
    AgentSnapshot, Decision, MarketSnapshot, decide,
)
from .orderbook import Fill, OrderBook
from .personas import Persona


log = logging.getLogger(__name__)


@dataclass
class AgentRuntime:
    agent_id: int
    persona: Persona
    cash: float
    yes_shares: float = 0.0
    no_shares: float = 0.0


@dataclass
class Simulation:
    sim_id: str
    market_id: str
    market_slug: str
    question: str
    description: str
    end_date_str: str
    market_resolved_yes: Optional[int]
    n_ticks: int
    taker_fee_bps: float
    agents: list[AgentRuntime]
    book_yes: OrderBook = field(default_factory=lambda: OrderBook("YES"))
    book_no: OrderBook = field(default_factory=lambda: OrderBook("NO"))

    yes_mid_history: list[float] = field(default_factory=list)
    no_mid_history: list[float] = field(default_factory=list)
    actions_log: list[tuple] = field(default_factory=list)
    fills_log: list[tuple] = field(default_factory=list)
    positions_log: list[tuple] = field(default_factory=list)

    @property
    def yes_mid(self) -> float:
        return self.book_yes.mid()

    @property
    def no_mid(self) -> float:
        return self.book_no.mid()


def make_sim(
    *,
    market_id: str, market_slug: str,
    question: str, description: str, end_date_str: str,
    market_resolved_yes: Optional[int],
    personas: list[Persona],
    n_ticks: int = 24, taker_fee_bps: float = 0.0,
    sim_id: Optional[str] = None,
) -> Simulation:
    sid = sim_id or uuid.uuid4().hex[:16]
    agents = [
        AgentRuntime(agent_id=i, persona=p, cash=p.capital_initial)
        for i, p in enumerate(personas)
    ]
    return Simulation(
        sim_id=sid, market_id=market_id, market_slug=market_slug,
        question=question, description=description, end_date_str=end_date_str,
        market_resolved_yes=market_resolved_yes,
        n_ticks=n_ticks, taker_fee_bps=taker_fee_bps, agents=agents,
    )


def _book_for(sim: Simulation, outcome: str) -> OrderBook:
    return sim.book_yes if outcome == "YES" else sim.book_no


def _shares_held(agent: AgentRuntime, outcome: str) -> float:
    return agent.yes_shares if outcome == "YES" else agent.no_shares


def _adjust_shares(agent: AgentRuntime, outcome: str, delta: float) -> None:
    if outcome == "YES":
        agent.yes_shares += delta
    else:
        agent.no_shares += delta


def _agent_resting_count(book: OrderBook, agent_id: int) -> int:
    return sum(
        1 for o in (book.bids + book.asks) if o.agent_id == agent_id
    )


def _execute_decision(
    sim: Simulation, agent: AgentRuntime, decision: Decision, tick: int,
) -> tuple[list[Fill], float, str]:
    """Apply decision against the appropriate book. Returns (fills,
    shares_traded, error_msg). shares_traded is signed: positive for
    BUY-side acquisitions, negative for SELL-side disposals (taker)."""
    book = _book_for(sim, decision.outcome)

    if decision.order_type == "HOLD" or decision.size_usd <= 0:
        return [], 0.0, ""

    if decision.order_type == "CANCEL":
        # Cancel ALL of this agent's resting orders on this outcome
        n = book.cancel_all_for_agent(agent.agent_id)
        return [], 0.0, f"cancelled={n}"

    side = decision.side  # 'BUY' or 'SELL'

    # --- Compute size in shares ---
    if decision.order_type == "LIMIT":
        # For LIMIT BUY:    cash budget / limit price
        # For LIMIT SELL:   capped by held shares
        if side == "BUY":
            if decision.price <= 0:
                return [], 0.0, "invalid_price"
            shares = min(decision.size_usd / decision.price, agent.cash / decision.price)
        else:  # SELL
            shares = min(decision.size_usd / max(decision.price, 1e-6),
                         _shares_held(agent, decision.outcome))
        if shares <= 0:
            return [], 0.0, "insufficient_resources"
        fills, _ = book.add_limit(
            agent_id=agent.agent_id, side=side, price=decision.price,
            size=shares, ts=tick,
        )
    else:  # MARKET
        if side == "BUY":
            best_ask = book.best_ask()
            if best_ask is None or best_ask <= 0:
                return [], 0.0, "no_liquidity"
            # estimate shares: cash budget / best ask (will refine via fill prices)
            cap_shares = min(decision.size_usd / best_ask, agent.cash / best_ask)
            fills, _ = book.add_market(agent.agent_id, "BUY", cap_shares, ts=tick)
        else:  # SELL
            best_bid = book.best_bid()
            if best_bid is None or best_bid <= 0:
                return [], 0.0, "no_liquidity"
            held = _shares_held(agent, decision.outcome)
            cap_shares = min(decision.size_usd / best_bid, held)
            fills, _ = book.add_market(agent.agent_id, "SELL", cap_shares, ts=tick)

    if not fills:
        return [], 0.0, ""

    # Apply fills to cash and shares for both sides
    shares_traded_taker = 0.0
    for f in fills:
        # Identify makers and takers among our sim agents
        # All fills update both sides in our agent registry where applicable.
        maker = next((a for a in sim.agents if a.agent_id == f.maker_agent_id), None)
        taker = next((a for a in sim.agents if a.agent_id == f.taker_agent_id), None)
        notional = f.price * f.size

        # Maker's side determines the direction:
        if maker is not None:
            if f.maker_side == "BUY":
                # Maker bought: gains shares, loses cash
                maker.cash -= notional
                _adjust_shares(maker, decision.outcome, +f.size)
            else:  # maker_side == 'SELL'
                maker.cash += notional
                _adjust_shares(maker, decision.outcome, -f.size)
        if taker is not None:
            taker_side = "BUY" if f.maker_side == "SELL" else "SELL"
            fee = notional * (sim.taker_fee_bps / 10000.0)
            if taker_side == "BUY":
                taker.cash -= notional + fee
                _adjust_shares(taker, decision.outcome, +f.size)
                shares_traded_taker += f.size
            else:
                taker.cash += notional - fee
                _adjust_shares(taker, decision.outcome, -f.size)
                shares_traded_taker -= f.size

        sim.fills_log.append((
            sim.sim_id, tick, f.maker_order_id, f.taker_order_id,
            f.maker_agent_id, f.taker_agent_id,
            decision.outcome, f.maker_side, f.price, f.size,
            notional, dt.datetime.utcnow(),
        ))

    return fills, shares_traded_taker, ""


def run_simulation(
    sim: Simulation,
    *,
    api_key: str, base_url: str, model: str,
    decide_fn=decide, log_progress: bool = True,
    rng: Optional[random.Random] = None,
) -> None:
    """Run all ticks. Mutates sim in place."""
    rng = rng or random.Random(0)
    for tick in range(sim.n_ticks):
        sim.yes_mid_history.append(sim.yes_mid)
        sim.no_mid_history.append(sim.no_mid)
        ticks_remaining = sim.n_ticks - tick

        # Decisions: each agent submits one in random order this tick
        order_idx = list(range(len(sim.agents)))
        rng.shuffle(order_idx)
        for slot, ai in enumerate(order_idx):
            agent = sim.agents[ai]
            market = MarketSnapshot(
                yes_best_bid=sim.book_yes.best_bid(),
                yes_best_ask=sim.book_yes.best_ask(),
                yes_mid=sim.yes_mid,
                no_best_bid=sim.book_no.best_bid(),
                no_best_ask=sim.book_no.best_ask(),
                no_mid=sim.no_mid,
                yes_mid_history=list(sim.yes_mid_history),
                ticks_remaining=ticks_remaining, total_ticks=sim.n_ticks,
            )
            agent_state = AgentSnapshot(
                agent_id=agent.agent_id, cash=agent.cash,
                yes_shares=agent.yes_shares, no_shares=agent.no_shares,
                n_resting_orders=(
                    _agent_resting_count(sim.book_yes, agent.agent_id)
                    + _agent_resting_count(sim.book_no, agent.agent_id)
                ),
            )
            decision = decide_fn(
                persona=agent.persona,
                question=sim.question, description=sim.description,
                end_date=sim.end_date_str,
                market=market, agent=agent_state,
                api_key=api_key, base_url=base_url, model=model,
            )
            yes_mid_before = sim.yes_mid
            fills, shares_taken, exec_err = _execute_decision(sim, agent, decision, tick)
            yes_mid_after = sim.yes_mid

            now = dt.datetime.utcnow()
            sim.actions_log.append((
                sim.sim_id, tick, agent.agent_id,
                decision.order_type, decision.outcome, decision.side,
                decision.price, decision.size_usd,
                yes_mid_before, yes_mid_after, shares_taken,
                len(fills),
                decision.reasoning, decision.raw_response,
                decision.api_latency_ms,
                decision.api_error or exec_err, now,
            ))
            if log_progress:
                err = decision.api_error or exec_err
                err_s = f" err={err}" if err else ""
                log.info(
                    "tick=%d ag=%d %s %s %s p=%.2f $%.0f → fills=%d yes_mid=%.3f%s",
                    tick, agent.agent_id, decision.order_type, decision.outcome,
                    decision.side, decision.price, decision.size_usd,
                    len(fills), yes_mid_after, err_s,
                )
        # Snapshot positions at tick end
        for agent in sim.agents:
            unrealized = (
                agent.yes_shares * sim.yes_mid
                + agent.no_shares * sim.no_mid
            )
            sim.positions_log.append((
                sim.sim_id, tick, agent.agent_id,
                agent.yes_shares, agent.no_shares, agent.cash,
                0.0, unrealized,
            ))


def settle(sim: Simulation) -> dict[int, float]:
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
