"""Full-book observer — debug / god-mode only.

Exposes the entire orderbook ladder + every agent's positions.
Should NEVER be used in a SERD-validated experiment because it lets
the LLM read other agents' resting orders directly.
"""
from __future__ import annotations

from environment.observers.quote_only import observe as _quote_only_observe


def observe(sim, agent_id: int):
    """v8 stub — currently identical to quote_only. v9 will return a
    god-mode dict with full bid/ask ladders + agent inventory leak.

    NOT for production runs."""
    return _quote_only_observe(sim, agent_id)
