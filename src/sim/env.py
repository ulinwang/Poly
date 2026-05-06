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


# v4: reserved id for environmental bootstrap maker. Excluded from SERD.
# Must be a non-negative UInt32 since agent_id columns are UInt32; we use
# a sentinel near the top of the range so it never collides with real
# round-robin agent ids (0..N-1).
ENV_MAKER_AGENT_ID = 999_999


@dataclass
class AgentRuntime:
    agent_id: int
    persona: Persona
    cash: float
    yes_shares: float = 0.0
    no_shares: float = 0.0
    # v4: optional private-signal layer. None means "agent has no
    # informational prior beyond what the prompt tells it".
    private_signal_mu: Optional[float] = None
    private_signal_sigma: Optional[float] = None
    # v4: source wallet address for traceability when calibrated.
    src_wallet_addr: str = ""


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
    personas: Optional[list[Persona]] = None,
    population: Optional[list] = None,
    n_ticks: int = 24, taker_fee_bps: float = 0.0,
    sim_id: Optional[str] = None,
) -> Simulation:
    """Build a fresh Simulation. Pass either:

    - `personas` (legacy v2/v3 path): list of Persona dataclasses; capital
      and behavior come solely from the persona constants.
    - `population` (v4 path): list of AgentInit (from
      `src.sim.initialization.build_population`), where each entry
      anchors the agent to a real on-chain wallet's pre-event features
      and carries an empirically derived private signal. The function
      synthesizes a Persona on-the-fly so the rest of the engine
      (decide loop, prompt builder) is unchanged.

    Exactly one of the two must be provided.
    """
    if (personas is None) == (population is None):
        raise ValueError("provide exactly one of personas or population")

    sid = sim_id or uuid.uuid4().hex[:16]
    agents: list[AgentRuntime] = []

    if personas is not None:
        for i, p in enumerate(personas):
            agents.append(AgentRuntime(agent_id=i, persona=p, cash=p.capital_initial))
    else:
        # population is a list[AgentInit]; lazy-import to avoid cycles
        for i, ai in enumerate(population):  # type: ignore[arg-type]
            persona = Persona(
                persona_type=ai.persona_type,
                risk_aversion=ai.risk_aversion,
                capital_initial=ai.capital_initial,
                profile_text=ai.profile_text,
            )
            agents.append(AgentRuntime(
                agent_id=i, persona=persona, cash=ai.capital_initial,
                private_signal_mu=ai.private_signal_mu,
                private_signal_sigma=ai.private_signal_sigma,
                src_wallet_addr=ai.wallet_addr,
            ))

    return Simulation(
        sim_id=sid, market_id=market_id, market_slug=market_slug,
        question=question, description=description, end_date_str=end_date_str,
        market_resolved_yes=market_resolved_yes,
        n_ticks=n_ticks, taker_fee_bps=taker_fee_bps, agents=agents,
    )


def seed_orderbook_liquidity(
    sim: Simulation,
    yes_anchor: float = 0.5, no_anchor: float = 0.5,
    spread: float = 0.04, depth_levels: int = 3, depth_per_level: float = 100.0,
) -> None:
    """Inject exogenous resting liquidity from a synthetic environmental
    market maker (agent_id = ENV_MAKER_AGENT_ID). Places a bid
    ladder below `*_anchor` and an ask ladder above, on BOTH books.

    Uses the existing OrderBook.add_limit API; produces no fills (both
    sides are passive resting orders). The seed orders are owned by
    agent_id=-1 so the SERD pipeline can exclude them.

    `depth_per_level` is in shares (since add_limit takes shares); a
    typical bid at 0.45 of size 100 = $45 of liquidity.
    """
    half = spread / 2.0
    for level in range(depth_levels):
        offset = half + level * 0.01
        # Round to tick (default 0.01) — must match orderbook.tick_size
        bid_y = round((yes_anchor - offset) * 100) / 100
        ask_y = round((yes_anchor + offset) * 100) / 100
        bid_n = round((no_anchor - offset) * 100) / 100
        ask_n = round((no_anchor + offset) * 100) / 100
        if 0 < bid_y < 1:
            sim.book_yes.add_limit(
                ENV_MAKER_AGENT_ID, "BUY", bid_y, depth_per_level, ts=-1,
            )
        if 0 < ask_y < 1:
            sim.book_yes.add_limit(
                ENV_MAKER_AGENT_ID, "SELL", ask_y, depth_per_level, ts=-1,
            )
        if 0 < bid_n < 1:
            sim.book_no.add_limit(
                ENV_MAKER_AGENT_ID, "BUY", bid_n, depth_per_level, ts=-1,
            )
        if 0 < ask_n < 1:
            sim.book_no.add_limit(
                ENV_MAKER_AGENT_ID, "SELL", ask_n, depth_per_level, ts=-1,
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

    # SPLIT/MERGE: on-chain CTF primitives that don't touch the orderbook.
    # SPLIT: pay $X cash -> get X YES + X NO shares (capped by cash).
    # MERGE: destroy X YES + X NO -> get $X cash (capped by min held).
    if decision.order_type == "SPLIT":
        amount = min(decision.size_usd, agent.cash)
        if amount <= 0:
            return [], 0.0, "insufficient_cash"
        agent.cash -= amount
        agent.yes_shares += amount
        agent.no_shares += amount
        return [], amount, ""

    if decision.order_type == "MERGE":
        pairs = min(decision.size_usd, agent.yes_shares, agent.no_shares)
        if pairs <= 0:
            return [], 0.0, "insufficient_pairs"
        agent.cash += pairs
        agent.yes_shares -= pairs
        agent.no_shares -= pairs
        return [], pairs, ""

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
            # Polymarket fee spec: fee = C * feeRate * p * (1 - p), where C is
            # shares and p is fill price. Symmetric around 0.5 and ~0 at
            # extremes (0.01 / 0.99). Maker pays no fee.
            fee = f.size * (sim.taker_fee_bps / 10000.0) * f.price * (1.0 - f.price)
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
                private_signal_mu=agent.private_signal_mu,
                private_signal_sigma=agent.private_signal_sigma,
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
