"""REDEEM: claim payout on resolved-side shares.

In the current sim, redemption happens implicitly at
`environment.settlement.settle()` once `market_resolved_yes` is set.
This tool exists for symmetry (Gym observation that an agent can
choose to redeem early when the resolution is known on-chain), but
v8 issues no on-tick redemptions — the runner calls `settle()` once
at end-of-sim.
"""
from __future__ import annotations

from agent.decision.types import Decision


def REDEEM(*, reasoning: str = "") -> Decision:
    """No-op marker Decision; runner ignores it pre-settlement.
    Reserved for v9 once the env supports mid-tick resolution."""
    return Decision(
        order_type="HOLD", outcome="YES", side="BUY",
        price=0.0, size_usd=0.0,
        reasoning=reasoning or "redeem (deferred to settle)",
        raw_response="", api_latency_ms=0, api_error="",
    )
