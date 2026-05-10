"""Conditional Token Framework primitives — SPLIT / MERGE.

These are off-orderbook actions: spending USDC to mint a YES+NO pair
(SPLIT), or destroying a matched pair to redeem USDC (MERGE).
Implementations mutate the AgentRuntime; on-chain redemption (REDEEM)
happens at `settlement.settle()` once the market resolves.
"""
from __future__ import annotations


def split(agent, amount_usd: float) -> tuple[float, str]:
    """Spend `amount_usd` to mint that many YES + NO shares each.
    Returns (minted_pairs, error_msg). Capped by agent.cash."""
    pairs = min(amount_usd, agent.cash)
    if pairs <= 0:
        return 0.0, "insufficient_cash"
    agent.cash -= pairs
    agent.yes_shares += pairs
    agent.no_shares += pairs
    return pairs, ""


def merge(agent, amount_pairs: float) -> tuple[float, str]:
    """Destroy `amount_pairs` of matched YES+NO shares for `amount_pairs`
    USDC. Capped by min(yes_shares, no_shares)."""
    pairs = min(amount_pairs, agent.yes_shares, agent.no_shares)
    if pairs <= 0:
        return 0.0, "insufficient_pairs"
    agent.cash += pairs
    agent.yes_shares -= pairs
    agent.no_shares -= pairs
    return pairs, ""
