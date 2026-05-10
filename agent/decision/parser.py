"""LLM JSON output → Decision-shape dict. No I/O."""
from __future__ import annotations

import json


VALID_ORDER_TYPES = {"LIMIT", "MARKET", "CANCEL", "HOLD", "SPLIT", "MERGE"}
VALID_OUTCOMES = {"YES", "NO"}
VALID_SIDES = {"BUY", "SELL"}


def round_to_tick(price: float, tick_size: float = 0.01) -> float:
    """Snap to the nearest tick. Polymarket default tick = 0.01."""
    if tick_size <= 0:
        return price
    return round(price / tick_size) * tick_size


def parse_decision(text: str, tick_size: float = 0.01) -> dict:
    """Strict-but-forgiving JSON extractor.

    Strips ```fences``` if the LLM ignored the no-fences instruction;
    coerces price into [0, 1] and snaps to tick; clamps size_usd ≥ 0.
    Raises ValueError on missing/unknown order_type — caller decides
    whether to retry or fall back.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError(f"no JSON object: {text[:200]!r}")
    obj = json.loads(text[start: end + 1])

    order_type = str(obj.get("order_type", "")).upper()
    if order_type not in VALID_ORDER_TYPES:
        raise ValueError(f"invalid order_type: {order_type!r}")

    if order_type in {"SPLIT", "MERGE"}:
        outcome = "YES"
        side = "BUY"
        price = 0.0
    else:
        outcome = str(obj.get("outcome", "YES")).upper()
        if outcome not in VALID_OUTCOMES:
            outcome = "YES"
        side = str(obj.get("side", "BUY")).upper()
        if side not in VALID_SIDES:
            side = "BUY"
        try:
            price = float(obj.get("price", 0.5))
        except (TypeError, ValueError):
            price = 0.5
        price = max(0.0, min(1.0, price))
        price = round_to_tick(price, tick_size=tick_size)

    try:
        size_usd = float(obj.get("size_usd", 0))
    except (TypeError, ValueError):
        size_usd = 0.0
    if size_usd < 0:
        size_usd = 0.0
    if order_type == "HOLD":
        size_usd = 0.0

    return {
        "order_type": order_type,
        "outcome": outcome,
        "side": side,
        "price": price,
        "size_usd": size_usd,
        "reasoning": str(obj.get("reasoning", "")).strip(),
    }
