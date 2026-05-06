"""
Logarithmic Market Scoring Rule (Hanson, 2003) — the standard
automated-market-maker for binary prediction markets.

State is two share counts q_yes, q_no (integers or floats; the AMM
holds the opposite side of every trade). The instantaneous YES price
is exp(q_yes/b) / (exp(q_yes/b) + exp(q_no/b)). The total cost the
AMM has paid out so far is C(q_yes, q_no) = b * ln(exp(q_yes/b) +
exp(q_no/b)). Buying delta_shares of YES costs C(q_yes+delta, q_no) -
C(q_yes, q_no), which is monotonic in delta and convex.

Choosing b: larger b = deeper liquidity = price moves less per share.
b=200 means buying ~$200 of YES at p=0.5 moves the price by ~0.05.
"""
from __future__ import annotations

import math
from typing import Literal


Side = Literal["YES", "NO"]


def _logsumexp_b(q_yes: float, q_no: float, b: float) -> float:
    # numerically stable: b * log(exp(qy/b) + exp(qn/b))
    m = max(q_yes, q_no) / b
    return b * (m + math.log(math.exp(q_yes / b - m) + math.exp(q_no / b - m)))


def cost(q_yes: float, q_no: float, b: float) -> float:
    """Total USD the AMM has spent given current outstanding shares."""
    return _logsumexp_b(q_yes, q_no, b)


def price_yes(q_yes: float, q_no: float, b: float) -> float:
    """Marginal YES price (∈ (0, 1)). YES + NO = 1 by construction."""
    # softmax(q_yes/b, q_no/b)[0]
    diff = (q_no - q_yes) / b
    # 1 / (1 + exp(diff))
    if diff >= 0:
        e = math.exp(-diff)
        return e / (1 + e)
    else:
        e = math.exp(diff)
        return 1 / (1 + e)


def price_no(q_yes: float, q_no: float, b: float) -> float:
    return 1.0 - price_yes(q_yes, q_no, b)


def cost_to_buy(side: Side, shares: float, q_yes: float, q_no: float, b: float) -> float:
    """USD cost to buy `shares` of `side` from the AMM. Sign convention:
    positive shares = buy, negative shares = sell back to AMM."""
    if side == "YES":
        return cost(q_yes + shares, q_no, b) - cost(q_yes, q_no, b)
    elif side == "NO":
        return cost(q_yes, q_no + shares, b) - cost(q_yes, q_no, b)
    else:
        raise ValueError(f"side must be 'YES' or 'NO', got {side!r}")


def shares_for_budget(
    side: Side,
    budget_usd: float,
    q_yes: float,
    q_no: float,
    b: float,
    max_iter: int = 64,
    tol: float = 1e-6,
) -> float:
    """Inverse of cost_to_buy: find shares such that cost ≈ budget_usd.
    Bisection on a monotonic function. Returns 0 for non-positive
    budget."""
    if budget_usd <= 0:
        return 0.0
    # Upper bound: budget / smallest plausible price (1/b for far-OTM)
    lo, hi = 0.0, max(budget_usd * 4, 10.0)
    # Expand hi if needed
    while cost_to_buy(side, hi, q_yes, q_no, b) < budget_usd and hi < 1e9:
        hi *= 2
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        c = cost_to_buy(side, mid, q_yes, q_no, b)
        if abs(c - budget_usd) < tol:
            return mid
        if c < budget_usd:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0
