"""MERGE: destroy a matched YES+NO pair to redeem USDC."""
from __future__ import annotations

from agent.decision.types import Decision


def MERGE(*, size_pairs: float, reasoning: str = "") -> Decision:
    return Decision(
        order_type="MERGE", outcome="YES", side="BUY", price=0.0,
        size_usd=float(size_pairs),
        reasoning=reasoning, raw_response="", api_latency_ms=0, api_error="",
    )
