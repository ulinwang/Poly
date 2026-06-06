"""Per-tick decision: state -> Decision.

Public API:
    decide(...)                       — one tick (uses tool calling)
    parse_decision(text, ...)         — legacy text-mode JSON parser
    parse_tool_call(tool_call, ...)   — v8.1 OpenAI tool-call parser
    call_deepseek(...)                — text-mode chat completion
    call_deepseek_with_tools(...)     — function-tool chat completion
    call_with_retry(...)              — exponential-backoff wrapper
    TOOL_SCHEMAS, NAME_TO_ORDER_TYPE  — function tool definitions
    AgentSnapshot, MarketSnapshot, Decision  — dataclasses
"""
from agent.decision.types import AgentSnapshot, Decision, MarketSnapshot
from agent.decision.parser import (
    parse_decision, parse_tool_call, round_to_tick,
    VALID_ORDER_TYPES, VALID_OUTCOMES, VALID_SIDES,
)
from agent.decision.llm import (
    call_deepseek, call_deepseek_with_tools, continue_with_tools,
)
from agent.decision.retry import call_with_retry
from agent.decision.runtime import MAX_INFO_TURNS, decide
from agent.decision.tool_schemas import (
    INFO_TOOL_NAME, NAME_TO_ORDER_TYPE, TOOL_SCHEMAS, select_tools,
)

__all__ = [
    "AgentSnapshot", "Decision", "MarketSnapshot",
    "parse_decision", "parse_tool_call", "round_to_tick",
    "VALID_ORDER_TYPES", "VALID_OUTCOMES", "VALID_SIDES",
    "call_deepseek", "call_deepseek_with_tools", "continue_with_tools",
    "call_with_retry",
    "decide", "MAX_INFO_TURNS",
    "TOOL_SCHEMAS", "NAME_TO_ORDER_TYPE", "INFO_TOOL_NAME", "select_tools",
]
