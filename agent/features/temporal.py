"""Time-window feature helpers.

Pure functions over `(t0, lifetime_secs)` to compute n_ticks and
related sim-time aggregates. v8 extracts these from
`derive_priors.market_lifetime_n_ticks`."""
from __future__ import annotations


def n_ticks_for_lifetime(
    open_ts: int, last_ts: int, fidelity_hours: int = 6,
    floor: int = 8, cap: int = 48,
) -> int:
    """Sim ticks = lifetime / fidelity, clamped to [floor, cap].

    `cap = 48` is a compute-budget choice (LLM cost), documented in
    `docs/EMPIRICAL_PRIORS.md`. `floor = 8` is the minimum needed
    for meaningful price discovery."""
    span_hours = max(fidelity_hours, (last_ts - open_ts) // 3600)
    n = round(span_hours / fidelity_hours)
    return max(floor, min(cap, n))
