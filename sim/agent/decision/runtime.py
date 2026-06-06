"""Per-tick decision runtime: persona + state → Decision.

v8.1: trader path uses OpenAI native tool calling. Persona generation
still uses the text path (see `agent.personas.calibrated`).

v14: when the belief tool is enabled, each tick is evaluated in two
LLM stages: first force an `update_belief` call, then ask for at most
one trade-related action (or no tool call = HOLD). This keeps the
agent's posterior explicit without hard-coding any trading rule.
"""
from __future__ import annotations

import json
import time
import urllib.error
from typing import Any, Callable, Optional

from agent.decision.llm import call_deepseek_with_tools, continue_with_tools
from agent.decision.parser import parse_belief_tool_call, parse_tool_call
from agent.decision.retry import call_with_retry
from agent.decision.tool_schemas import INFO_TOOL_NAME, TOOL_SCHEMAS
from agent.decision.types import AgentSnapshot, Decision, MarketSnapshot
from agent.info import SearchResult, search_web
from agent.personas.persona import Persona
from agent.prompt.builder import build_clob_system_prompt, build_user_prompt


# Max number of read-tool (get_information) round-trips allowed per tick
# before we force the LLM to converge on a trade/HOLD action.
MAX_INFO_TURNS = 2

# Callback the runner injects to log the actual search query + results
# (the `agent_info_query` event). Signature: (query, results) -> None.
InfoQueryCallback = Callable[[str, list[SearchResult]], None]


def _tool_name(tool: dict) -> str:
    return str(tool.get("function", {}).get("name", ""))


def _split_belief_and_trade_tools(
    tools: list[dict],
) -> tuple[list[dict], list[dict]]:
    belief_tools = [t for t in tools if _tool_name(t) == "update_belief"]
    trade_tools = [t for t in tools if _tool_name(t) != "update_belief"]
    return belief_tools, trade_tools


def _forced_tool_choice(name: str) -> dict[str, dict[str, str] | str]:
    return {"type": "function", "function": {"name": name}}


def _tool_calls(result: dict) -> list[dict]:
    calls = result.get("tool_calls") or []
    if calls:
        return list(calls)
    call = result.get("tool_call")
    return [call] if call else []


def _parse_belief_result(result: dict) -> dict | None:
    for tc in _tool_calls(result):
        bu = parse_belief_tool_call(tc)
        if bu is not None:
            return bu
    return None


def _stage_raw(**stages: dict | None) -> str:
    return json.dumps(
        {name: (stage or {}).get("raw", "") for name, stage in stages.items()},
        ensure_ascii=False,
    )


def _append_belief_stage_prompt(user_prompt: str, prompt_language: str = "en") -> str:
    if prompt_language == "zh":
        return (
            f"{user_prompt}\n\n"
            "决策阶段 1/2：请先更新你当前对 P(YES) 的信念。"
            "调用 `update_belief`，给出 posterior、confidence 和简短 rationale。"
            "本阶段不要选择任何交易动作。"
        )
    return (
        f"{user_prompt}\n\n"
        "Decision stage 1 of 2: first update your current belief about "
        "P(YES). Call `update_belief` with your posterior, confidence, "
        "and short rationale. Do not choose a trading action in this stage."
    )


def _append_trade_stage_prompt(
    user_prompt: str, belief_update: dict, prompt_language: str = "en",
) -> str:
    yes_prob = float(belief_update["yes_prob"])
    confidence = float(belief_update["confidence"])
    rationale = str(belief_update.get("rationale", ""))
    if prompt_language == "zh":
        return (
            f"{user_prompt}\n\n"
            "本 tick 的决策阶段 1/2 已完成：\n"
            f"  P(YES) = {yes_prob:.3f}\n"
            f"  Confidence = {confidence:.2f}\n"
            f"  Rationale = \"{rationale}\"\n\n"
            "决策阶段 2/2：基于这个信念，判断现在是否执行一个交易相关动作。"
            "你可以调用且只调用一个可用交易工具，也可以不调用工具表示 HOLD。"
            "请根据你的 persona、持仓、当前盘口和风险自主判断。"
        )
    return (
        f"{user_prompt}\n\n"
        "Decision stage 1 of 2 already completed this tick:\n"
        f"  P(YES) = {yes_prob:.3f}\n"
        f"  Confidence = {confidence:.2f}\n"
        f"  Rationale = \"{rationale}\"\n\n"
        "Decision stage 2 of 2: using that belief, decide whether to "
        "take one trading-related action now. You may call exactly one "
        "available trade tool, or call no tool to HOLD. Choose freely "
        "based on your persona, portfolio, current book, and risk."
    )


def _format_search_results(results: list[SearchResult]) -> str:
    """Render search results as a compact text block fed back to the LLM."""
    lines = []
    for i, r in enumerate(results, 1):
        url = f" ({r.url})" if r.url else ""
        lines.append(f"{i}. {r.title}{url}\n   {r.snippet}")
    return "\n".join(lines) if lines else "(no results)"


def _assistant_tool_call_message(tool_call: dict) -> dict:
    """Build the assistant message that records a single tool call, in the
    OpenAI/litellm wire format, so it can be appended to `messages` and
    paired with the matching `role: "tool"` result message."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": tool_call.get("id") or "call_get_information",
            "type": "function",
            "function": {
                "name": tool_call.get("name", ""),
                "arguments": json.dumps(
                    tool_call.get("arguments") or {}, ensure_ascii=False,
                ),
            },
        }],
    }


def _tool_result_message(tool_call: dict, content: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call.get("id") or "call_get_information",
        "name": tool_call.get("name", ""),
        "content": content,
    }


def _run_trade_stage_with_info(
    *,
    call_fn,
    continue_fn,
    base_call_kwargs: dict,
    max_attempts: int,
    system_prompt: str,
    trade_user_prompt: str,
    trade_tools: list[dict],
    tick_size: float,
    search_backend,
    on_info_query: Optional[InfoQueryCallback],
) -> dict:
    """Trade stage with a bounded read-tool (get_information) loop.

    The LLM may call `get_information(query)`; we run a live web search,
    feed the results back as a tool-result message, and let it decide again
    — at most `MAX_INFO_TURNS` times. After the budget is exhausted we make
    one final call that *excludes* the info tool so the LLM must converge on
    a trade tool or HOLD.

    Returns the final trade-stage result dict (same shape as call_fn).
    """
    # First trade-stage call (info tool included via trade_tools).
    result = call_with_retry(
        call_fn,
        max_attempts=max_attempts,
        **base_call_kwargs,
        system_prompt=system_prompt,
        user_prompt=trade_user_prompt,
        tools=trade_tools,
        tool_choice="auto",
    )

    info_call = _info_tool_call(result)
    if info_call is None:
        return result

    # Enter the multi-turn loop: rebuild the conversation as explicit
    # messages so we can append assistant tool_calls + tool results.
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": trade_user_prompt},
    ]
    # Trade tools WITHOUT the info tool — used to force convergence.
    trade_tools_no_info = [
        t for t in trade_tools
        if t.get("function", {}).get("name") != INFO_TOOL_NAME
    ]

    turns = 0
    while info_call is not None and turns < MAX_INFO_TURNS:
        turns += 1
        query = str((info_call.get("arguments") or {}).get("query", "")).strip()
        results = search_web(query, backend=search_backend, max_results=5)
        if on_info_query is not None:
            try:
                on_info_query(query, results)
            except Exception:        # noqa: BLE001 — logging must not break the tick
                pass

        messages.append(_assistant_tool_call_message(info_call))
        messages.append(_tool_result_message(
            info_call,
            "Web search results for "
            f"\"{query}\":\n{_format_search_results(results)}",
        ))

        last_turn = turns >= MAX_INFO_TURNS
        # On the last allowed turn, drop the info tool and force a decision
        # so the loop is guaranteed to converge (bounded by MAX_INFO_TURNS).
        result = call_with_retry(
            continue_fn,
            max_attempts=max_attempts,
            **base_call_kwargs,
            messages=messages,
            tools=(trade_tools_no_info if last_turn else trade_tools),
            tool_choice="auto",
        )
        info_call = None if last_turn else _info_tool_call(result)

    return result


def _info_tool_call(result: dict) -> dict | None:
    """Return the get_information tool call from a result, or None."""
    for tc in _tool_calls(result):
        if str(tc.get("name", "")) == INFO_TOOL_NAME:
            return tc
    return None


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
    continue_fn=continue_with_tools,
    tools: list[dict] | None = None,
    thinking: bool | None = None,
    prompt_language: str = "en",
    info_enabled: bool = True,
    search_backend=None,
    on_info_query: Optional[InfoQueryCallback] = None,
) -> Decision:
    """One tick. Returns a Decision (HOLD on unrecoverable failure).

    `call_fn` is injectable for tests; default is the live OpenAI
    tool-calling path. `continue_fn` is the multi-turn continuation call
    (also injectable). `tools` defaults to `TOOL_SCHEMAS`.

    If `info_enabled` and the `get_information` tool is among `tools`, the
    trade stage runs a bounded read-tool loop: the LLM may web-search for
    context (via `search_backend`, default chosen from env), the results are
    fed back, and it decides again — at most `MAX_INFO_TURNS` round trips.
    `on_info_query(query, results)` is called for each search so the runner
    can log it (`agent_info_query` event) for auditability. Web search is
    NOT bit-for-bit reproducible; logging the query+results preserves
    auditability instead.
    """
    if tools is None:
        tools = TOOL_SCHEMAS
    belief_tools, trade_tools = _split_belief_and_trade_tools(tools)
    info_in_tools = any(_tool_name(t) == INFO_TOOL_NAME for t in trade_tools)
    use_info_loop = info_enabled and info_in_tools

    system_prompt = build_clob_system_prompt(
        persona, question, description, end_date, tick_size=tick_size,
        prompt_language=prompt_language,
    )
    user_prompt = build_user_prompt(
        market, agent, prompt_language=prompt_language,
    )

    started = time.time()
    raw = ""
    api_error = ""
    parsed = {
        "order_type": "HOLD", "outcome": "YES", "side": "BUY",
        "price": 0.5, "size_usd": 0.0, "reasoning": "",
    }
    belief_update = None
    try:
        base_call_kwargs: dict[str, Any] = dict(
            base_url=base_url, api_key=api_key, model=model,
            temperature=temperature, timeout=timeout,
        )
        if thinking is not None:
            base_call_kwargs["thinking"] = thinking

        if belief_tools:
            belief_result = call_with_retry(
                call_fn,
                max_attempts=max_attempts,
                **base_call_kwargs,
                system_prompt=system_prompt,
                user_prompt=_append_belief_stage_prompt(
                    user_prompt, prompt_language,
                ),
                tools=belief_tools,
                tool_choice=_forced_tool_choice("update_belief"),
            )
            belief_update = _parse_belief_result(belief_result)
            if belief_update is None:
                raw = _stage_raw(belief_stage=belief_result)
                parsed["reasoning"] = (
                    belief_result.get("text", "")[:280]
                    or "belief_stage_missing_update_belief"
                )
                api_error = "parse: missing update_belief in belief stage"
            else:
                if trade_tools:
                    trade_user_prompt = _append_trade_stage_prompt(
                        user_prompt, belief_update, prompt_language,
                    )
                    if use_info_loop:
                        trade_result = _run_trade_stage_with_info(
                            call_fn=call_fn,
                            continue_fn=continue_fn,
                            base_call_kwargs=base_call_kwargs,
                            max_attempts=max_attempts,
                            system_prompt=system_prompt,
                            trade_user_prompt=trade_user_prompt,
                            trade_tools=trade_tools,
                            tick_size=tick_size,
                            search_backend=search_backend,
                            on_info_query=on_info_query,
                        )
                    else:
                        trade_tools_eff = [
                            t for t in trade_tools
                            if _tool_name(t) != INFO_TOOL_NAME
                        ]
                        trade_result = call_with_retry(
                            call_fn,
                            max_attempts=max_attempts,
                            **base_call_kwargs,
                            system_prompt=system_prompt,
                            user_prompt=trade_user_prompt,
                            tools=trade_tools_eff,
                            tool_choice="auto",
                        )
                    raw = _stage_raw(
                        belief_stage=belief_result,
                        trade_stage=trade_result,
                    )
                    parsed = parse_tool_call(
                        trade_result.get("tool_call"), tick_size=tick_size,
                    )
                    # If the LLM put prose in `text` (e.g. tool_choice=auto
                    # and it declined to call), pin it as the reasoning so
                    # we don't lose the trace.
                    if not parsed["reasoning"] and trade_result.get("text"):
                        parsed["reasoning"] = trade_result["text"][:280]
                else:
                    raw = _stage_raw(belief_stage=belief_result)
                    parsed = {
                        "order_type": "UPDATE_BELIEF", "outcome": "YES",
                        "side": "BUY", "price": belief_update["yes_prob"],
                        "size_usd": 0.0,
                        "reasoning": belief_update.get("rationale", ""),
                    }
        else:
            if use_info_loop:
                # No belief stage: run the info loop directly on the full
                # tool set (belief tool already absent here).
                result = _run_trade_stage_with_info(
                    call_fn=call_fn,
                    continue_fn=continue_fn,
                    base_call_kwargs=base_call_kwargs,
                    max_attempts=max_attempts,
                    system_prompt=system_prompt,
                    trade_user_prompt=user_prompt,
                    trade_tools=tools,
                    tick_size=tick_size,
                    search_backend=search_backend,
                    on_info_query=on_info_query,
                )
            else:
                tools_eff = [
                    t for t in tools if _tool_name(t) != INFO_TOOL_NAME
                ]
                result = call_with_retry(
                    call_fn,
                    max_attempts=max_attempts,
                    **base_call_kwargs,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    tools=tools_eff,
                    tool_choice="auto",
                )
            raw = result.get("raw", "")
            parsed = parse_tool_call(result.get("tool_call"), tick_size=tick_size)
            # Back-compat path for configs that disable the explicit
            # two-stage belief tool.
            if parsed["order_type"] != "UPDATE_BELIEF":
                belief_update = _parse_belief_result(result)
            else:
                belief_update = parsed.get("belief_update")
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
        belief_update=belief_update,
    )
