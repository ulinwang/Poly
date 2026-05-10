"""Per-tick decision runtime: persona + state → Decision.

Composes the prompt builder, LLM client, parser, and retry layer.
The simulator (`environment.env.PolyEnv.step`) calls `decide(...)` for
each agent and feeds the resulting Decision into the orderbook.
"""
from __future__ import annotations

import json
import time
import urllib.error

from agent.decision.llm import call_deepseek
from agent.decision.parser import parse_decision
from agent.decision.retry import call_with_retry
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
    call_fn=call_deepseek,
) -> Decision:
    """One tick. Returns a Decision (HOLD on unrecoverable failure)."""
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
            temperature=temperature, timeout=timeout,
            response_format={"type": "json_object"},
            max_attempts=max_attempts,
        )
        raw = result["raw"]
        parsed = parse_decision(result["text"], tick_size=tick_size)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        api_error = f"http: {exc}"
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        api_error = f"parse: {exc}"

    latency_ms = int((time.time() - started) * 1000)
    return Decision(
        order_type=parsed["order_type"], outcome=parsed["outcome"],
        side=parsed["side"], price=parsed["price"],
        size_usd=parsed["size_usd"], reasoning=parsed["reasoning"],
        raw_response=raw, api_latency_ms=latency_ms, api_error=api_error,
    )
