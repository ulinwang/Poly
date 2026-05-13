"""OpenAI-compatible function tool schemas the LLM sees per tick.

Five tools (HOLD = no tool call, see runtime.decide). Each
`function.name` matches the dispatcher in `parser.parse_tool_call`,
which converts a `tool_calls[0]` object → the legacy
parsed-decision dict shape that `environment.env._execute_decision`
already understands. This means the existing CLOB engine, fee math,
CTF primitives, and SERD pipeline are all unchanged.

`temperature=0.0` is enforced upstream in
`agent.decision.runtime.decide`.
"""
from __future__ import annotations


_TOOL_PLACE_LIMIT = {
    "type": "function",
    "function": {
        "name": "place_limit_order",
        "description": (
            "Place a price-time-priority limit order on the YES or NO "
            "outcome book. Crosses the spread if your price beats the "
            "best opposite quote, else rests on the book until matched "
            "or cancelled. Cash (BUY) or shares (SELL) are reserved at "
            "placement and only released on fill or CANCEL. Use when "
            "you have a price target and are willing to wait."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "outcome": {
                    "type": "string", "enum": ["YES", "NO"],
                    "description": "Which outcome book to act on.",
                },
                "side": {
                    "type": "string", "enum": ["BUY", "SELL"],
                    "description": "Direction within that book.",
                },
                "price": {
                    "type": "number", "minimum": 0.01, "maximum": 0.99,
                    "description": (
                        "Limit price in [0.01, 0.99]. Snapped to the "
                        "market's tick size by the parser."
                    ),
                },
                "size_usd": {
                    "type": "number", "minimum": 0,
                    "description": "USD notional intent.",
                },
                "reasoning": {
                    "type": "string",
                    "description": "1–2 sentence justification in your persona's voice.",
                },
            },
            "required": ["outcome", "side", "price", "size_usd"],
        },
    },
}

_TOOL_PLACE_MARKET = {
    "type": "function",
    "function": {
        "name": "place_market_order",
        "description": (
            "Sweep the best opposite side immediately, filling against "
            "resting orders until `size_usd` is exhausted or the book "
            "runs dry (immediate-or-cancel). Use when you need "
            "execution NOW and accept slippage."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "enum": ["YES", "NO"]},
                "side": {"type": "string", "enum": ["BUY", "SELL"]},
                "size_usd": {"type": "number", "minimum": 0},
                "reasoning": {"type": "string"},
            },
            "required": ["outcome", "side", "size_usd"],
        },
    },
}

_TOOL_CANCEL = {
    "type": "function",
    "function": {
        "name": "cancel_orders",
        "description": (
            "Cancel ALL of your resting limit orders on the given "
            "(outcome, side). Frees the reserved cash or inventory. "
            "Useful if your prior price view changed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "enum": ["YES", "NO"]},
                "side": {"type": "string", "enum": ["BUY", "SELL"]},
                "reasoning": {"type": "string"},
            },
            "required": ["outcome", "side"],
        },
    },
}

_TOOL_SPLIT = {
    "type": "function",
    "function": {
        "name": "split_position",
        "description": (
            "Conditional Token primitive: spend `size_usd` USDC to "
            "mint that many YES shares AND that many NO shares "
            "simultaneously (1:1:1). Useful for two-sided market "
            "making — you now have inventory on both sides."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "size_usd": {"type": "number", "minimum": 0},
                "reasoning": {"type": "string"},
            },
            "required": ["size_usd"],
        },
    },
}

_TOOL_UPDATE_BELIEF = {
    "type": "function",
    "function": {
        "name": "update_belief",
        "description": (
            "Record your current posterior over YES outcome before (or "
            "in addition to) any trade. Use this each tick when your "
            "view changes. Calling update_belief alone (without a trade "
            "tool) counts as a HOLD with a belief update."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "yes_prob": {
                    "type": "number", "minimum": 0.01, "maximum": 0.99,
                },
                "confidence": {
                    "type": "number", "minimum": 0.0, "maximum": 1.0,
                    "description": "0 = epistemic floor, 1 = certain",
                },
                "rationale": {"type": "string", "maxLength": 300},
            },
            "required": ["yes_prob", "confidence", "rationale"],
        },
    },
}

_TOOL_MERGE = {
    "type": "function",
    "function": {
        "name": "merge_position",
        "description": (
            "Conditional Token primitive: destroy a matched pair "
            "(`size_pairs` of YES + same of NO) to redeem `size_pairs` "
            "USDC. The inverse of split_position. Capped by your "
            "minimum-of-(yes_shares, no_shares)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "size_pairs": {"type": "number", "minimum": 0},
                "reasoning": {"type": "string"},
            },
            "required": ["size_pairs"],
        },
    },
}


TOOL_SCHEMAS = [
    _TOOL_PLACE_LIMIT,
    _TOOL_PLACE_MARKET,
    _TOOL_CANCEL,
    _TOOL_SPLIT,
    _TOOL_MERGE,
    _TOOL_UPDATE_BELIEF,
]


def select_tools(*, belief_update_enabled: bool = True) -> list[dict]:
    """v13 (B4): return TOOL_SCHEMAS, optionally without the belief tool.

    Used by the runner to honour ExperimentConfig.agent.belief_update_enabled.
    """
    if belief_update_enabled:
        return TOOL_SCHEMAS
    return [t for t in TOOL_SCHEMAS if t["function"]["name"] != "update_belief"]


# Map function name → engine `order_type`. Used by parser.parse_tool_call.
# v13 (AGT-4): `update_belief` is dispatched specially — it sets the
# agent's posterior on AgentRuntime and emits an UPDATE_BELIEF action
# row but does NOT touch the orderbook (semantically a HOLD with side
# effects).
NAME_TO_ORDER_TYPE = {
    "place_limit_order":  "LIMIT",
    "place_market_order": "MARKET",
    "cancel_orders":      "CANCEL",
    "split_position":     "SPLIT",
    "merge_position":     "MERGE",
    "update_belief":      "UPDATE_BELIEF",
}
