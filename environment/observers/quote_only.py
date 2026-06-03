"""Default observer: quotes + public microstructure + own state.

Information given to the agent: public top-of-book quotes, aggregated
book depth, recent public fills, and the agent's own portfolio/order
history. It never exposes other agents' private positions or identities.
"""
from __future__ import annotations

from agent.decision.types import AgentSnapshot, MarketSnapshot


DEPTH_LEVELS = 5
MEMORY_DEPTH = 5
FILL_TAPE_DEPTH = 5


def _remaining(order) -> float:
    return float(getattr(order, "remaining", getattr(order, "size", 0.0)))


def _side_depth(book, side: str, levels: int = DEPTH_LEVELS) -> list[dict]:
    if hasattr(book, "depth_at"):
        return [
            {"price": float(price), "size": float(size)}
            for price, size in book.depth_at(side, levels=levels)
        ]
    orders = book.bids if side == "BUY" else book.asks
    out: list[dict] = []
    for order in orders:
        if not out or out[-1]["price"] != float(order.price):
            if len(out) >= levels:
                break
            out.append({"price": float(order.price), "size": 0.0})
        out[-1]["size"] += _remaining(order)
    return out


def _imbalance(bid_depth: list[dict], ask_depth: list[dict]) -> float | None:
    bid = sum(float(x["size"]) for x in bid_depth)
    ask = sum(float(x["size"]) for x in ask_depth)
    total = bid + ask
    if total <= 0:
        return None
    return (bid - ask) / total


def _current_tick(sim) -> int:
    ticks_remaining = getattr(sim, "_ticks_remaining", sim.n_ticks)
    return max(0, int(sim.n_ticks - ticks_remaining))


def _own_resting_orders(sim, agent_id: int) -> list[dict]:
    tick = _current_tick(sim)
    rows: list[dict] = []
    for outcome, book in (("YES", sim.book_yes), ("NO", sim.book_no)):
        for side, orders in (("BUY", book.bids), ("SELL", book.asks)):
            for order in orders:
                if order.agent_id != agent_id:
                    continue
                rows.append({
                    "outcome": outcome,
                    "side": side,
                    "price": float(order.price),
                    "remaining": _remaining(order),
                    "age_ticks": max(0, tick - int(getattr(order, "ts", tick))),
                })
    return rows[:10]


def _recent_fills(sim) -> list[dict]:
    rows: list[dict] = []
    for r in list(getattr(sim, "fills_log", []) or [])[-FILL_TAPE_DEPTH:]:
        rows.append({
            "tick": int(r[1]),
            "outcome": str(r[6]),
            "maker_side": str(r[7]),
            "price": float(r[8]),
            "size": float(r[9]),
            "notional": float(r[10]),
        })
    return rows


def _recent_own_fills(sim, agent_id: int) -> list[dict]:
    rows: list[dict] = []
    for r in list(getattr(sim, "fills_log", []) or []):
        maker_id = int(r[4])
        taker_id = int(r[5])
        if agent_id not in {maker_id, taker_id}:
            continue
        role = "maker" if maker_id == agent_id else "taker"
        rows.append({
            "tick": int(r[1]),
            "role": role,
            "outcome": str(r[6]),
            "maker_side": str(r[7]),
            "price": float(r[8]),
            "size": float(r[9]),
            "notional": float(r[10]),
        })
    return rows[-FILL_TAPE_DEPTH:]


def observe(sim, agent_id: int) -> tuple[MarketSnapshot, AgentSnapshot]:
    """Quote-only observation. `sim` is the env's Simulation object."""
    agent = next((a for a in sim.agents if a.agent_id == agent_id), None)
    if agent is None:
        raise KeyError(f"unknown agent_id {agent_id}")

    yes_bid_depth = _side_depth(sim.book_yes, "BUY")
    yes_ask_depth = _side_depth(sim.book_yes, "SELL")
    no_bid_depth = _side_depth(sim.book_no, "BUY")
    no_ask_depth = _side_depth(sim.book_no, "SELL")

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
        yes_bid_depth=yes_bid_depth,
        yes_ask_depth=yes_ask_depth,
        no_bid_depth=no_bid_depth,
        no_ask_depth=no_ask_depth,
        yes_order_imbalance=_imbalance(yes_bid_depth, yes_ask_depth),
        no_order_imbalance=_imbalance(no_bid_depth, no_ask_depth),
        recent_fills=_recent_fills(sim),
    )

    n_resting = sum(
        1 for o in (sim.book_yes.bids + sim.book_yes.asks
                    + sim.book_no.bids + sim.book_no.asks)
        if o.agent_id == agent_id
    )
    # v10.1: copy the last MEMORY_DEPTH entries from agent.memory so
    # the LLM can see its own recent actions (fixes the CANCEL spam).
    recent = list(getattr(agent, "memory", []) or [])[-MEMORY_DEPTH:]

    # v13 (AGT-4): copy the agent's current explicit belief, if any,
    # so the prompt builder can render "Your current stated belief".
    belief_snapshot = getattr(agent, "belief", None)
    belief_copy = dict(belief_snapshot) if belief_snapshot else None

    state = AgentSnapshot(
        agent_id=agent.agent_id, cash=agent.cash,
        yes_shares=agent.yes_shares, no_shares=agent.no_shares,
        n_resting_orders=n_resting,
        private_signal_mu=agent.private_signal_mu,
        private_signal_sigma=agent.private_signal_sigma,
        recent_decisions=recent,
        resting_orders=_own_resting_orders(sim, agent_id),
        recent_own_fills=_recent_own_fills(sim, agent_id),
        belief_snapshot=belief_copy,
    )
    return market, state
