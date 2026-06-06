"""Polymarket fee math.

Taker fee = `C × rate × p × (1−p)` (paper §2.1, Polymarket /markets
docs). Symmetric around 0.5; ~0 at the 0.01/0.99 extremes. Maker
pays no fee. The fee rate is a per-market float fetched from
`clob_markets.taker_base_fee` and propagated via priors JSON.
"""
from __future__ import annotations


def taker_fee(size: float, price: float, fee_bps: float) -> float:
    """USD fee for a taker fill of `size` shares at `price`. `fee_bps`
    is basis points (clob_markets convention)."""
    rate = fee_bps / 10_000.0
    return size * rate * price * (1.0 - price)
