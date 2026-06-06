"""SPLIT: spend USDC to mint a 1:1 YES/NO pair."""
from __future__ import annotations

from agent.decision.types import Decision


def SPLIT(*, size_usd: float, reasoning: str = "") -> Decision:
    return Decision(
        order_type="SPLIT", outcome="YES", side="BUY", price=0.0,
        size_usd=float(size_usd),
        reasoning=reasoning, raw_response="", api_latency_ms=0, api_error="",
    )
