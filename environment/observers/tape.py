"""Quote-only + recent fills (the tape). v9 expansion.

Adds the last K fills from `sim.fills_log` as a side-channel. Not
used by the v8 SERD baseline (which would conflate observable signal
with persona effect). Kept here as a stub so config files can request
it without import errors; falls back to quote_only behavior."""
from __future__ import annotations

from environment.observers.quote_only import observe as _quote_only_observe


def observe(sim, agent_id: int):
    """v8 stub — currently identical to quote_only. v9 will append a
    truncated `recent_fills` list to MarketSnapshot.tape."""
    return _quote_only_observe(sim, agent_id)
