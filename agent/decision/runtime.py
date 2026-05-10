"""Per-tick decision runtime: persona + state → Decision.

v8.1: trader path uses OpenAI native tool calling. The LLM either
calls one of the 5 tools (LIMIT / MARKET / CANCEL / SPLIT / MERGE)
or declines (= HOLD). Persona generation still uses the text path
(see `agent.personas.calibrated`).
"""
from __future__ import annotations

import json
import time
import urllib.error

from agent.decision.llm import call_deepseek_with_tools
from agent.decision.parser import parse_tool_call
from agent.decision.retry import call_with_retry
from agent.decision.tool_schemas import TOOL_SCHEMAS
from agent.decision.types import AgentSnapshot, Decision, MarketSnapshot
from agent.personas.persona import Persona
from agent.prompt.builder import build_clob_system_prompt, build_user_prompt


def decide(
    *,
    persona: Persona,
    question: str,
    description: str,
    end_date: str,
    market: MarketSnapshot,
    agent: AgentSnapshot,
    api_key: str,
    base_url: str,
    model: str,
    tick_size: float = 0.01,
    temperature: float = 0.0,
    timeout: float = 120.0,
    max_attempts: int = 3,
    call_fn=call_deepseek_with_tools,
    tools: list[dict] | None = None,
) -> Decision:
    """One tick. Returns a Decision (HOLD on unrecoverable failure).

    `call_fn` is injectable for tests; default is the live OpenAI
    tool-calling path. `tools` defaults to `TOOL_SCHEMAS`.
    """
    if tools is None:
        tools = TOOL_SCHEMAS

    system_prompt = build_clob_system_prompt(
        persona, question, description, end_date, tick_size=tick_size,
    )
    user_prompt = build_user_prompt(market, agent)

    started = time.time()
    raw = ""
    api_error = ""
    parsed = {
        "order_type": "HOLD", "outcome": "YES", "side": "BUY",
        "price": 0.5, "size_usd": 0.0, "reasoning": "",
    }
    try:
        result = call_with_retry(
            call_fn,
            base_url=base_url, api_key=api_key, model=model,
            system_prompt=system_prompt, user_prompt=user_prompt,
            tools=tools,
            temperature=temperature, timeout=timeout,
            max_attempts=max_attempts,
        )
        raw = result.get("raw", "")
        parsed = parse_tool_call(result.get("tool_call"), tick_size=tick_size)
        # If the LLM put prose in `text` (e.g. tool_choice=auto and it
        # declined to call), pin it as the reasoning so we don't lose
        # the trace.
        if not parsed["reasoning"] and result.get("text"):
            parsed["reasoning"] = result["text"][:280]
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        api_error = f"http: {exc}"
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        api_error = f"parse: {exc}"
    except Exception as exc:                # noqa: BLE001
        # OpenAI SDK exceptions (RateLimitError / APIError / etc.) —
        # call_with_retry already exhausted them.
        api_error = f"sdk: {type(exc).__name__}: {exc}"

    latency_ms = int((time.time() - started) * 1000)
    return Decision(
        order_type=parsed["order_type"], outcome=parsed["outcome"],
        side=parsed["side"], price=parsed["price"],
        size_usd=parsed["size_usd"], reasoning=parsed["reasoning"],
        raw_response=raw, api_latency_ms=latency_ms, api_error=api_error,
    )
