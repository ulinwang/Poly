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

from agent.decision import (
    AgentSnapshot, Decision, MarketSnapshot, decide,
)
from agent.personas.persona import Persona
from environment.ctf import split as ctf_split, merge as ctf_merge
from environment.fees import taker_fee
from environment.orderbook import Fill, OrderBook
from environment.settlement import settle as _settle


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
    # v5: cash and inventory committed to *resting* LIMIT orders (not
    # yet filled, not yet cancelled). Available cash for new orders is
    # `cash - cash_reserved`; available shares is
    # `<outcome>_shares - <outcome>_reserved`.
    cash_reserved: float = 0.0
    yes_reserved: float = 0.0
    no_reserved: float = 0.0
    # v10.1: episodic memory — list of compact dicts summarizing the
    # agent's recent decisions, written by env.step after each tick.
    # Read by the prompt builder; the LLM sees the last MEMORY_DEPTH
    # entries to avoid blind self-cancellation.
    memory: list = None  # default_factory in __post_init__ to keep
    # the dataclass default order stable

    def __post_init__(self):
        if self.memory is None:
            self.memory = []


def available_cash(a: "AgentRuntime") -> float:
    return a.cash - a.cash_reserved


def available_shares(a: "AgentRuntime", outcome: str) -> float:
    return (a.yes_shares - a.yes_reserved) if outcome == "YES" \
           else (a.no_shares - a.no_reserved)


def _adjust_reserved_shares(a: "AgentRuntime", outcome: str, delta: float) -> None:
    if outcome == "YES":
        a.yes_reserved += delta
    else:
        a.no_reserved += delta


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

    if decision.order_type == "HOLD":
        return [], 0.0, ""
    # CANCEL has size_usd=0 by design; do NOT short-circuit on size.
    if decision.order_type != "CANCEL" and decision.size_usd <= 0:
        return [], 0.0, ""

    if decision.order_type == "CANCEL":
        # Cancel ALL of this agent's resting orders on this outcome
        # and release the cash / inventory that was reserved for them.
        cancels = book.cancel_all_for_agent(agent.agent_id)
        for ci in cancels:
            if ci.side == "BUY":
                agent.cash_reserved = max(0.0, agent.cash_reserved
                                          - ci.price * ci.remaining_size)
            else:  # SELL
                _adjust_reserved_shares(agent, decision.outcome,
                                        -ci.remaining_size)
        return [], 0.0, f"cancelled={len(cancels)}"

    # SPLIT/MERGE: on-chain CTF primitives that don't touch the orderbook.
    # SPLIT: pay $X cash -> get X YES + X NO shares (capped by cash).
    # MERGE: destroy X YES + X NO -> get $X cash (capped by min held).
    if decision.order_type == "SPLIT":
        pairs, err = ctf_split(agent, decision.size_usd)
        return [], pairs, err

    if decision.order_type == "MERGE":
        pairs, err = ctf_merge(agent, decision.size_usd)
        return [], pairs, err

    side = decision.side  # 'BUY' or 'SELL'

    # --- Compute size in shares ---
    if decision.order_type == "LIMIT":
        # LIMIT placement honors v5 reservations: only the AVAILABLE
        # (un-reserved) cash / inventory can back a new resting order.
        # For LIMIT BUY:    capped by available_cash / limit price.
        # For LIMIT SELL:   capped by available_shares of that outcome.
        if side == "BUY":
            if decision.price <= 0:
                return [], 0.0, "invalid_price"
            cap_usd = min(decision.size_usd, available_cash(agent))
            shares = cap_usd / decision.price
        else:  # SELL
            cap_shares_inventory = available_shares(agent, decision.outcome)
            shares = min(decision.size_usd / max(decision.price, 1e-6),
                         cap_shares_inventory)
        if shares <= 0:
            return [], 0.0, "insufficient_resources"
        fills, order = book.add_limit(
            agent_id=agent.agent_id, side=side, price=decision.price,
            size=shares, ts=tick,
        )
        # The portion that did NOT fill rests on the book. Reserve
        # cash / inventory for it so it can't be re-spent by a later
        # action this tick or in future ticks.
        if order.remaining > 1e-9:
            if side == "BUY":
                agent.cash_reserved += order.remaining * decision.price
            else:
                _adjust_reserved_shares(agent, decision.outcome,
                                        +order.remaining)
    else:  # MARKET
        if side == "BUY":
            best_ask = book.best_ask()
            if best_ask is None or best_ask <= 0:
                return [], 0.0, "no_liquidity"
            # estimate shares: budget / best ask (will refine via
            # fill prices). Use available_cash, not raw cash.
            cap_shares = min(decision.size_usd / best_ask,
                             available_cash(agent) / best_ask)
            fills, _ = book.add_market(agent.agent_id, "BUY", cap_shares, ts=tick)
        else:  # SELL
            best_bid = book.best_bid()
            if best_bid is None or best_bid <= 0:
                return [], 0.0, "no_liquidity"
            cap_shares = min(decision.size_usd / best_bid,
                             available_shares(agent, decision.outcome))
            fills, _ = book.add_market(agent.agent_id, "SELL", cap_shares, ts=tick)

    # Drain any same-agent maker cancellations the orderbook flagged
    # while matching this order (NASDAQ-style cancel-resting). The
    # cancelled maker had cash / inventory reserved at placement; we
    # must release it here.
    if book.self_match_cancellations:
        for ci in book.self_match_cancellations:
            owner = next((a for a in sim.agents
                          if a.agent_id == ci.agent_id), None)
            if owner is None:
                continue
            if ci.side == "BUY":
                owner.cash_reserved = max(
                    0.0, owner.cash_reserved - ci.price * ci.remaining_size,
                )
            else:
                _adjust_reserved_shares(owner, decision.outcome,
                                        -ci.remaining_size)
        book.self_match_cancellations.clear()

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
                # Maker bought: gains shares, loses cash. Release the
                # cash that had been reserved for this resting order.
                maker.cash -= notional
                maker.cash_reserved = max(0.0, maker.cash_reserved - notional)
                _adjust_shares(maker, decision.outcome, +f.size)
            else:  # maker_side == 'SELL'
                # Maker sold: gains cash, loses shares. Release the
                # shares that had been reserved.
                maker.cash += notional
                _adjust_shares(maker, decision.outcome, -f.size)
                _adjust_reserved_shares(maker, decision.outcome, -f.size)
                maker.yes_reserved = max(0.0, maker.yes_reserved)
                maker.no_reserved = max(0.0, maker.no_reserved)
        if taker is not None:
            taker_side = "BUY" if f.maker_side == "SELL" else "SELL"
            # Polymarket fee spec lives in environment.fees.taker_fee:
            # symmetric around 0.5, ~0 at the 0.01/0.99 extremes.
            fee = taker_fee(f.size, f.price, sim.taker_fee_bps)
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
            # Episodic memory: action + reasoning. The reasoning is the
            # LLM's own update on its market view; carrying it across
            # ticks gives the agent persistent belief continuity.
            if getattr(agent, "memory", None) is not None:
                agent.memory.append({
                    "tick": tick, "action": decision.order_type,
                    "outcome": decision.outcome, "side": decision.side,
                    "price": float(decision.price), "size_usd": float(decision.size_usd),
                    "fills": len(fills), "yes_mid_after": float(yes_mid_after),
                    "reasoning": (decision.reasoning or "").strip()[:240],
                })
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
    """Re-export of `environment.settlement.settle` so existing
    callers `from environment.env import settle` keep working."""
    return _settle(sim)


# ============================================================
# Gym-style facade — v8.
# ============================================================

class PolyEnv:
    """Gym-ish wrapper over the imperative simulator.

    Lifecycle:
        env = PolyEnv(market_meta=..., population=...)
        obs = env.reset(seed=0)            # dict[agent_id, (Market, Agent)]
        for tick in range(env.n_ticks):
            actions = {agent_id: Decision(...), ...}    # one per agent
            obs, info = env.step(actions)
        pnl = env.settle()                 # dict[agent_id, float]

    The internal `Simulation` is exposed via `env.state` (read-only
    snapshot) for testing / persistence / SERD network construction.
    Action dispatch reuses `_execute_decision`; v9 will collapse that
    into the per-tool dispatch in `environment.tools/*`.
    """

    def __init__(
        self,
        *,
        market_meta: dict,
        population: list,
        n_ticks: int,
        taker_fee_bps: float = 0.0,
        sim_id: Optional[str] = None,
        observer: str = "quote_only",
    ):
        self._market_meta = market_meta
        self._population = population
        self.n_ticks = int(n_ticks)
        self.taker_fee_bps = float(taker_fee_bps)
        self._sim_id = sim_id
        self._observer = observer
        self.sim: Optional[Simulation] = None
        self._tick = 0
        self._rng: Optional[random.Random] = None

    def reset(self, seed: int = 0) -> dict:
        """Build a fresh Simulation. Returns initial observations
        keyed by agent_id."""
        self.sim = make_sim(
            market_id=self._market_meta["condition_id"],
            market_slug=self._market_meta.get("slug", ""),
            question=self._market_meta.get("question", ""),
            description=self._market_meta.get("description", ""),
            end_date_str=self._market_meta.get("end_date_iso", ""),
            market_resolved_yes=self._market_meta.get("winning_idx"),
            population=self._population,
            n_ticks=self.n_ticks, taker_fee_bps=self.taker_fee_bps,
            sim_id=self._sim_id,
        )
        # Reset auxiliary clocks
        setattr(self.sim, "_ticks_remaining", self.n_ticks)
        self._tick = 0
        self._rng = random.Random(seed)
        return self._observations()

    def step(self, actions: dict[int, Decision]) -> tuple[dict, dict]:
        """Apply one tick of `{agent_id: Decision}`. Returns
        (observations, info)."""
        if self.sim is None:
            raise RuntimeError("call .reset(seed) before .step()")
        sim = self.sim
        sim.yes_mid_history.append(sim.yes_mid)
        sim.no_mid_history.append(sim.no_mid)
        setattr(sim, "_ticks_remaining", self.n_ticks - self._tick)

        order_idx = list(range(len(sim.agents)))
        self._rng.shuffle(order_idx)              # type: ignore[union-attr]
        n_fills = 0
        for ai in order_idx:
            agent = sim.agents[ai]
            decision = actions.get(agent.agent_id)
            if decision is None:
                continue
            yes_mid_before = sim.yes_mid
            fills, shares_taken, exec_err = _execute_decision(
                sim, agent, decision, self._tick,
            )
            yes_mid_after = sim.yes_mid
            n_fills += len(fills)
            sim.actions_log.append((
                sim.sim_id, self._tick, agent.agent_id,
                decision.order_type, decision.outcome, decision.side,
                decision.price, decision.size_usd,
                yes_mid_before, yes_mid_after, shares_taken,
                len(fills),
                decision.reasoning, decision.raw_response,
                decision.api_latency_ms,
                decision.api_error or exec_err, dt.datetime.utcnow(),
            ))
            # Episodic memory: action + reasoning (belief carrier).
            if getattr(agent, "memory", None) is not None:
                agent.memory.append({
                    "tick": self._tick,
                    "action": decision.order_type,
                    "outcome": decision.outcome,
                    "side": decision.side,
                    "price": float(decision.price),
                    "size_usd": float(decision.size_usd),
                    "fills": len(fills),
                    "yes_mid_after": float(yes_mid_after),
                    "reasoning": (decision.reasoning or "").strip()[:240],
                })

        for agent in sim.agents:
            unrealized = (
                agent.yes_shares * sim.yes_mid
                + agent.no_shares * sim.no_mid
            )
            sim.positions_log.append((
                sim.sim_id, self._tick, agent.agent_id,
                agent.yes_shares, agent.no_shares, agent.cash,
                0.0, unrealized,
            ))
        self._tick += 1
        return self._observations(), {"n_fills": n_fills, "tick": self._tick}

    def _observations(self) -> dict:
        from environment.tools.observe import observe as obs_fn
        return {
            a.agent_id: obs_fn(self.sim, a.agent_id, observer=self._observer)
            for a in self.sim.agents
        }

    @property
    def state(self) -> Simulation:
        if self.sim is None:
            raise RuntimeError("env not yet reset; state unavailable")
        return self.sim

    def settle(self) -> dict[int, float]:
        if self.sim is None:
            raise RuntimeError("env not yet reset")
        return _settle(self.sim)
