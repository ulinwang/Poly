"""Per-agent / per-persona PnL aggregation.

v8: thin helpers on top of `environment.settle()`. v9 will extend
this to per-tick mark-to-market PnL paths and persona-level
aggregations consumed by `experiments.plots.pnl_distribution`.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def aggregate_by_persona(
    pnl: dict[int, float],
    persona_of: dict[int, str],
) -> dict[str, dict]:
    """Group {agent_id: pnl} by persona type. Returns
    {persona_type: {"n", "mean", "median", "min", "max"}}.
    """
    by_p: dict[str, list[float]] = defaultdict(list)
    for aid, value in pnl.items():
        by_p[persona_of.get(aid, "Unknown")].append(value)

    out: dict[str, dict] = {}
    for ptype, values in by_p.items():
        if not values:
            continue
        sorted_v = sorted(values)
        n = len(values)
        out[ptype] = {
            "n": n,
            "mean": sum(values) / n,
            "median": sorted_v[n // 2],
            "min": min(values),
            "max": max(values),
        }
    return out


def total_traded_volume(fills: Iterable[tuple], fill_price_idx: int = 8,
                        fill_size_idx: int = 9) -> float:
    """Total notional traded across the fill log. Defaults match the
    sim's fills_log tuple shape:
    (sim_id, tick, maker_oid, taker_oid, maker_aid, taker_aid,
     outcome, maker_side, price, size, notional, ts).
    """
    return sum(float(f[fill_price_idx]) * float(f[fill_size_idx])
               for f in fills)
