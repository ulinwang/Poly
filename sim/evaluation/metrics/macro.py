"""Macro (market-price level) metrics.

`compute_tick_metrics` runs live, once per tick. `market_eval` summarizes a
finished run. Kept dependency-light (schema + stdlib) so it can be imported
from both the live runner and post-hoc analysis.
"""
from __future__ import annotations

from statistics import pstdev
from typing import Optional, Sequence

from evaluation.schema import MarketEval, TickMetrics


def compute_tick_metrics(
    tick: int,
    yes_mid: float,
    no_mid: float,
    n_fills: int,
    prev_yes_mid: Optional[float],
) -> TickMetrics:
    """One TickMetrics row from the current market mids."""
    return TickMetrics(
        tick=tick,
        yes_mid=float(yes_mid),
        no_mid=float(no_mid),
        parity_gap=float(yes_mid) + float(no_mid) - 1.0,
        n_fills=int(n_fills),
        ret=0.0 if prev_yes_mid is None else float(yes_mid) - float(prev_yes_mid),
    )


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    xs, ys = xs[:n], ys[:n]
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx ** 0.5 * vy ** 0.5)


def market_eval(
    yes_mid_history: Sequence[float],
    real_path: Optional[Sequence[float]] = None,
) -> MarketEval:
    """Macro scorecard for a finished run.

    `real_path` (the bucket-aligned real Polymarket YES path) enables the
    calibration fields; omit it and they stay None.
    """
    hist = [float(x) for x in yes_mid_history] or [0.5]
    rets = [hist[i] - hist[i - 1] for i in range(1, len(hist))]
    ev = MarketEval(
        n_ticks=len(hist),
        final_yes_mid=hist[-1],
        max_yes_mid=max(hist),
        min_yes_mid=min(hist),
        realized_vol=pstdev(rets) if len(rets) > 1 else 0.0,
    )
    if real_path:
        rp = [float(x) for x in real_path]
        n = min(len(hist), len(rp))
        if n >= 1:
            ev.pearson_r = _pearson(hist[:n], rp[:n])
            ev.mae = sum(abs(hist[i] - rp[i]) for i in range(n)) / n
            ev.final_diff = hist[n - 1] - rp[n - 1]
            ev.direction_correct = (hist[n - 1] - 0.5) * (rp[n - 1] - 0.5) >= 0
    return ev
