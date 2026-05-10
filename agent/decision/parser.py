"""LLM output → Decision-shape dict. No I/O.

Two entry points:
  parse_decision(text, ...)        — legacy text-mode JSON parser
  parse_tool_call(tool_call, ...)  — v8.1 OpenAI tool-call parser

Both return the SAME dict shape so the rest of the engine
(`environment.env._execute_decision`) stays unchanged."""
from __future__ import annotations

import json

from agent.decision.tool_schemas import NAME_TO_ORDER_TYPE


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


def _hold_decision(reasoning: str = "") -> dict:
    return {
        "order_type": "HOLD", "outcome": "YES", "side": "BUY",
        "price": 0.0, "size_usd": 0.0, "reasoning": reasoning,
    }


def parse_tool_call(tool_call: dict | None, tick_size: float = 0.01) -> dict:
    """Convert one OpenAI `tool_call` dict (from
    `agent.decision.llm.call_deepseek_with_tools`) into the engine's
    parsed-decision shape. Returns HOLD if `tool_call` is None
    (LLM declined to act).

    Expected shape: {"name": str, "arguments": dict, "id": str}.

    SIZE/PRICE coercion mirrors `parse_decision`: prices clamped to
    [0,1] and tick-snapped, size clamped to ≥ 0.
    """
    if not tool_call:
        return _hold_decision()

    name = str(tool_call.get("name", ""))
    args = tool_call.get("arguments") or {}
    if not isinstance(args, dict):
        # arguments came in as a JSON string (some clients do this);
        # the LLM module should have already json-parsed it, but be
        # defensive.
        try:
            args = json.loads(args)
        except Exception:           # noqa: BLE001
            args = {}

    order_type = NAME_TO_ORDER_TYPE.get(name)
    if order_type is None:
        # Unknown tool — treat as HOLD with a diagnostic reason.
        return _hold_decision(reasoning=f"unknown_tool:{name}")

    reasoning = str(args.get("reasoning", "")).strip()

    if order_type in {"SPLIT", "MERGE"}:
        # SPLIT uses size_usd; MERGE uses size_pairs (semantically pairs,
        # but we store on the same `size_usd` field downstream because
        # the engine treats them as equivalent for this primitive).
        try:
            size = float(args.get("size_usd", args.get("size_pairs", 0)))
        except (TypeError, ValueError):
            size = 0.0
        size = max(0.0, size)
        return {
            "order_type": order_type, "outcome": "YES", "side": "BUY",
            "price": 0.0, "size_usd": size, "reasoning": reasoning,
        }

    outcome = str(args.get("outcome", "YES")).upper()
    if outcome not in VALID_OUTCOMES:
        outcome = "YES"
    side = str(args.get("side", "BUY")).upper()
    if side not in VALID_SIDES:
        side = "BUY"

    if order_type == "CANCEL":
        return {
            "order_type": "CANCEL", "outcome": outcome, "side": side,
            "price": 0.0, "size_usd": 0.0, "reasoning": reasoning,
        }

    try:
        size_usd = float(args.get("size_usd", 0))
    except (TypeError, ValueError):
        size_usd = 0.0
    size_usd = max(0.0, size_usd)

    if order_type == "MARKET":
        return {
            "order_type": "MARKET", "outcome": outcome, "side": side,
            "price": 0.0, "size_usd": size_usd, "reasoning": reasoning,
        }

    # LIMIT
    try:
        price = float(args.get("price", 0.5))
    except (TypeError, ValueError):
        price = 0.5
    price = max(0.0, min(1.0, price))
    price = round_to_tick(price, tick_size=tick_size)
    return {
        "order_type": "LIMIT", "outcome": outcome, "side": side,
        "price": price, "size_usd": size_usd, "reasoning": reasoning,
    }
