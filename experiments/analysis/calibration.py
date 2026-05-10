"""
Compute comparison metrics between the simulated price path and the
real Polymarket trade history.

Kept dependency-light (no numpy/scipy) so the project remains portable;
metrics are simple Pearson correlation and bucket-aligned price paths.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Sequence


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    denom = math.sqrt(sxx * syy)
    if denom == 0:
        return 0.0
    return sxy / denom


def real_price_path(
    trades: Sequence[tuple],
    n_buckets: int,
    start: dt.datetime,
    end: dt.datetime,
) -> list[float]:
    """Bucket real trades into n_buckets even windows between [start, end]
    and return the average YES-equivalent price per bucket. trades is a
    sequence of (..., trade_time, side, price, size, ...) tuples; we
    look at indices 2/3/4. Buckets without trades inherit the previous
    bucket's price (or 0.5 initially)."""
    if not trades or n_buckets <= 0 or end <= start:
        return [0.5] * n_buckets
    span = (end - start).total_seconds()
    bucket_size = span / n_buckets
    sums = [0.0] * n_buckets
    counts = [0] * n_buckets
    for t in trades:
        trade_time, _side, price, size = t[2], t[3], t[4], t[5]
        offset = (trade_time - start).total_seconds()
        if offset < 0 or offset > span:
            continue
        idx = min(int(offset // bucket_size), n_buckets - 1)
        weight = float(size) if size > 0 else 1.0
        sums[idx] += float(price) * weight
        counts[idx] += weight  # using weight as denom keeps it volume-weighted
    out: list[float] = []
    last = 0.5
    for s, c in zip(sums, counts):
        if c > 0:
            last = s / c
        out.append(last)
    return out


def compare_paths(
    sim_path: Sequence[float], real_path: Sequence[float]
) -> dict[str, float]:
    if len(sim_path) != len(real_path):
        raise ValueError(
            f"path lengths differ: sim={len(sim_path)} real={len(real_path)}"
        )
    return {
        "pearson_r": pearson(list(sim_path), list(real_path)),
        "mae": sum(abs(s - r) for s, r in zip(sim_path, real_path)) / len(sim_path),
        "final_diff": sim_path[-1] - real_path[-1],
    }


def direction_correct(
    sim_final_yes_price: float, market_resolved_yes: int
) -> bool:
    """True if the sim ended on the correct side of 0.5 for the eventual
    outcome."""
    if market_resolved_yes == 1:
        return sim_final_yes_price > 0.5
    return sim_final_yes_price < 0.5
