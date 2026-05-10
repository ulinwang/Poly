"""LIMIT and MARKET order builders."""
from __future__ import annotations

from agent.decision.types import Decision


def LIMIT(
    *,
    outcome: str, side: str, price: float, size_usd: float,
    reasoning: str = "",
) -> Decision:
    """Build a LIMIT-order Decision. Resting orders rest on the book
    until matched or cancelled. `price` MUST be a tick-aligned float
    in [0, 1]."""
    return Decision(
        order_type="LIMIT", outcome=outcome.upper(), side=side.upper(),
        price=float(price), size_usd=float(size_usd),
        reasoning=reasoning, raw_response="", api_latency_ms=0, api_error="",
    )


def MARKET(
    *,
    outcome: str, side: str, size_usd: float,
    reasoning: str = "",
) -> Decision:
    """Build a MARKET-order Decision (IOC sweep of the best opposite
    side until size is consumed)."""
    return Decision(
        order_type="MARKET", outcome=outcome.upper(), side=side.upper(),
        price=0.0, size_usd=float(size_usd),
        reasoning=reasoning, raw_response="", api_latency_ms=0, api_error="",
    )
