"""CANCEL: drop ALL of an agent's resting orders on (outcome, side)."""
from __future__ import annotations

from agent.decision.types import Decision


def CANCEL(*, outcome: str, side: str, reasoning: str = "") -> Decision:
    """Cancel-all on `(outcome, side)`. size_usd is intentionally 0."""
    return Decision(
        order_type="CANCEL", outcome=outcome.upper(), side=side.upper(),
        price=0.0, size_usd=0.0,
        reasoning=reasoning, raw_response="", api_latency_ms=0, api_error="",
    )
