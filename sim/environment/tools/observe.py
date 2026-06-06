"""Observation builder — composes a per-agent (MarketSnapshot,
AgentSnapshot) tuple from the sim state.

v8: this is the canonical entry the Gym `step()` calls. It picks the
observer (quote_only/tape/full_book) and packages it.
"""
from __future__ import annotations

from agent.decision.types import AgentSnapshot, MarketSnapshot
from environment.observers.quote_only import observe as observe_quote_only


_OBSERVERS = {
    "quote_only": observe_quote_only,
}


def observe(sim, agent_id: int, observer: str = "quote_only") -> tuple[MarketSnapshot, AgentSnapshot]:
    """Build (market_snapshot, agent_snapshot) using the named observer.

    Currently registered: "quote_only" (default). "tape" and
    "full_book" load lazily from `environment.observers.*` when their
    files are populated; falling back to quote_only if absent."""
    fn = _OBSERVERS.get(observer)
    if fn is None:
        try:
            mod = __import__(
                f"environment.observers.{observer}",
                fromlist=["observe"],
            )
            fn = mod.observe
            _OBSERVERS[observer] = fn
        except (ImportError, AttributeError):
            fn = observe_quote_only
    return fn(sim, agent_id)
