"""Crude token counting + truncation. Real tokenizer is model-specific;
this is a rule-of-thumb for budget-checking before we send."""
from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 chars for English-ish text."""
    return max(1, len(text) // 4)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate to roughly `max_tokens`, preserving a tail marker."""
    if estimate_tokens(text) <= max_tokens:
        return text
    keep = max_tokens * 4 - 32
    return text[:keep] + "\n…[truncated]"
