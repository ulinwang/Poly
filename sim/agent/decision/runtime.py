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
from agent.decision.tool_schemas import (
    FORUM_ACTION_TOOL_NAMES,
    FORUM_COMMENT_TOOL_NAME,
    FORUM_FOLLOW_TOOL_NAME,
    FORUM_POST_TOOL_NAME,
    FORUM_READ_TOOL_NAME,
    FORUM_TOOL_NAMES,
    INFO_TOOL_NAME,
    TOOL_SCHEMAS,
)
from agent.decision.types import AgentSnapshot, Decision, MarketSnapshot
from agent.info import SearchResult, search_web
from agent.personas.persona import Persona
from agent.prompt.builder import build_clob_system_prompt, build_user_prompt


# Max number of read-tool round-trips (get_information AND read_forum,
# combined) allowed per tick before we force the LLM to converge on a
# trade/HOLD action. This bounds the read part of the loop.
MAX_INFO_TURNS = 2

# Max number of *record* social actions (post_to_forum / comment_on_post /
# follow_user) an agent may take per tick. Prevents an agent from spamming
# the forum or looping forever on social actions. The loop also has a hard
# overall turn cap (MAX_INFO_TURNS + K_SOCIAL + 1) as a final safety bound.
K_SOCIAL = 2

# Callback the runner injects to log the actual search query + results
# (the `agent_info_query` event). Signature: (query, results) -> None.
InfoQueryCallback = Callable[[str, list[SearchResult]], None]

# Callback the runner injects to log each applied forum action (so the
# runner can emit forum_post / forum_comment / forum_follow events).
# Signature: (kind, payload) -> None, where kind ∈
# {"post", "comment", "follow"} and payload is a small dict.
ForumActionCallback = Callable[[str, dict], None]


def _tool_name(tool: dict) -> str:
    return str(tool.get("function", {}).get("name", ""))


def _drop_loop_tools(
    tools: list[dict], *, info: bool, forum: bool,
) -> list[dict]:
    """Return `tools` with the non-terminating loop tools removed.

    `info=True` drops `get_information`; `forum=True` drops the four forum
    tools. Used to keep info-only / forum-disabled paths behaving exactly
    as before and to strip tools the agent must not be able to call.
    """
    drop: set[str] = set()
    if info:
        drop.add(INFO_TOOL_NAME)
    if forum:
        drop |= set(FORUM_TOOL_NAMES)
    return [t for t in tools if _tool_name(t) not in drop]


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


def _read_or_social_call(result: dict) -> dict | None:
    """Return the first non-terminating tool call (get_information,
    read_forum, or a forum record action), or None.

    These are the calls that keep the bounded trade-stage loop going; any
    other tool call (a trade tool) is a terminal decision.
    """
    for tc in _tool_calls(result):
        name = str(tc.get("name", ""))
        if name == INFO_TOOL_NAME or name in FORUM_TOOL_NAMES:
            return tc
    return None


def _format_feed(forum, agent_id: int, limit: int = 5) -> str:
    """Render an agent's forum feed as a compact text block fed back to the
    LLM. Followed authors are prioritised (see Forum.read)."""
    posts = forum.get_feed_for(agent_id, limit=limit)
    if not posts:
        return "(forum is empty — no posts yet)"
    followed = forum.followed_by(agent_id)
    lines: list[str] = []
    for p in posts:
        tag = " [followed]" if p.author_id in followed else ""
        lines.append(
            f"post #{p.id} by agent {p.author_id}{tag} (tick {p.tick}): "
            f"{p.content}"
        )
        for c in forum.comments_for(p.id, limit=2):
            lines.append(
                f"    ↳ comment #{c.id} by agent {c.author_id}: {c.content}"
            )
    return "\n".join(lines)


def _apply_forum_action(
    *, forum, agent_id: int, tick: int, tool_call: dict,
    on_forum_action: Optional[ForumActionCallback],
    activity: dict | None = None,
) -> str:
    """Apply one forum record action (post / comment / follow) to `forum`
    and return a short confirmation string to feed back to the LLM. Invokes
    `on_forum_action(kind, payload)` so the runner can emit an event, and
    records the action into `activity` (for the agent's social memory).

    Mutations are deterministic; only the text content is LLM-generated.
    """
    name = str(tool_call.get("name", ""))
    args = tool_call.get("arguments") or {}

    def _notify(kind: str, payload: dict) -> None:
        if on_forum_action is None:
            return
        try:
            on_forum_action(kind, payload)
        except Exception:        # noqa: BLE001 — logging must not break the tick
            pass

    if name == FORUM_POST_TOOL_NAME:
        content = str(args.get("content", "")).strip()
        if not content:
            return "post_to_forum: empty content, nothing posted."
        post = forum.post(agent_id, content, tick)
        _notify("post", {
            "tick": tick, "author_id": agent_id,
            "post_id": post.id, "content": content,
        })
        if activity is not None:
            activity["posts"].append({
                "tick": tick, "post_id": post.id, "content": content,
            })
        return f"Posted to forum as post #{post.id}."

    if name == FORUM_COMMENT_TOOL_NAME:
        try:
            post_id = int(args.get("post_id"))
        except (TypeError, ValueError):
            return "comment_on_post: invalid post_id."
        content = str(args.get("content", "")).strip()
        if not content:
            return "comment_on_post: empty content, nothing posted."
        c = forum.comment(agent_id, post_id, content, tick)
        if c is None:
            return f"comment_on_post: post #{post_id} not found."
        _notify("comment", {
            "tick": tick, "author_id": agent_id, "post_id": post_id,
            "comment_id": c.id, "content": content,
        })
        return f"Commented on post #{post_id} as comment #{c.id}."

    if name == FORUM_FOLLOW_TOOL_NAME:
        try:
            target_id = int(args.get("agent_id"))
        except (TypeError, ValueError):
            return "follow_user: invalid agent_id."
        created = forum.follow(agent_id, target_id)
        if created:
            _notify("follow", {
                "tick": tick, "agent_id": agent_id, "target_id": target_id,
            })
            if activity is not None:
                activity["follows"].append(target_id)
            return f"Now following agent {target_id}."
        return f"Already following (or cannot follow) agent {target_id}."

    return f"unknown_forum_action:{name}"


def _run_trade_stage_loop(
    *,
    call_fn,
    continue_fn,
    base_call_kwargs: dict,
    max_attempts: int,
    system_prompt: str,
    trade_user_prompt: str,
    trade_tools: list[dict],
    tick_size: float,
    use_info: bool,
    search_backend,
    on_info_query: Optional[InfoQueryCallback],
    forum=None,
    agent_id: Optional[int] = None,
    tick: int = 0,
    on_forum_action: Optional[ForumActionCallback] = None,
) -> tuple[dict, dict]:
    """Trade stage with a single bounded multi-turn read/social loop.

    The LLM may interleave:
      * `get_information(query)` — live web search (read tool),
      * `read_forum(topic?)`     — returns its forum feed (read tool),
      * `post_to_forum` / `comment_on_post` / `follow_user` — record
        actions that mutate `sim.forum`.
    Each such call is answered with a tool-result message and the LLM is
    asked to continue. The loop is bounded by THREE limits so it always
    converges to a trade tool or HOLD:
      * at most `MAX_INFO_TURNS` read-tool round trips (web + forum reads),
      * at most `K_SOCIAL` record social actions,
      * a hard overall turn cap (belt-and-braces).
    When a budget is exhausted we drop the now-disallowed tools from the
    tool list so the LLM is forced to either keep using the still-allowed
    tools or finalise a trade/HOLD.

    Returns ``(result, activity)`` where `result` is the final trade-stage
    result dict (same shape as call_fn) and `activity` is the forum
    activity collected this tick (posts / reads / follows), for folding
    into the agent's social memory.
    """
    forum_enabled = forum is not None and agent_id is not None
    activity: dict = {"posts": [], "reads": [], "follows": []}
    # First trade-stage call (read/social tools included via trade_tools).
    result = call_with_retry(
        call_fn,
        max_attempts=max_attempts,
        **base_call_kwargs,
        system_prompt=system_prompt,
        user_prompt=trade_user_prompt,
        tools=trade_tools,
        tool_choice="auto",
    )

    pending = _read_or_social_call(result)
    if pending is None:
        return result, activity

    # Enter the multi-turn loop: rebuild the conversation as explicit
    # messages so we can append assistant tool_calls + tool results.
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": trade_user_prompt},
    ]

    read_turns = 0      # get_information + read_forum
    social_actions = 0  # post / comment / follow
    # Hard overall cap so a misbehaving model cannot loop forever even if
    # it alternates between the two budgets.
    hard_cap = MAX_INFO_TURNS + K_SOCIAL + 1
    total_turns = 0

    while pending is not None and total_turns < hard_cap:
        total_turns += 1
        name = str(pending.get("name", ""))
        args = pending.get("arguments") or {}

        # --- produce the tool-result content for this call ---
        if name == INFO_TOOL_NAME:
            read_turns += 1
            query = str(args.get("query", "")).strip()
            results = search_web(query, backend=search_backend, max_results=5)
            if on_info_query is not None:
                try:
                    on_info_query(query, results)
                except Exception:        # noqa: BLE001
                    pass
            tool_content = (
                f"Web search results for \"{query}\":\n"
                f"{_format_search_results(results)}"
            )
        elif name == FORUM_READ_TOOL_NAME:
            read_turns += 1
            if forum_enabled:
                topic = str(args.get("topic", "")).strip()
                hint = f" (topic: {topic})" if topic else ""
                feed = forum.get_feed_for(agent_id)
                followed = forum.followed_by(agent_id)
                # Record what was read into social memory (newest posts the
                # agent saw), flagging followed authors for priority.
                for p in feed:
                    activity["reads"].append({
                        "tick": p.tick, "post_id": p.id,
                        "author_id": p.author_id, "content": p.content,
                        "followed": p.author_id in followed,
                    })
                tool_content = (
                    f"Your forum feed{hint} (followed authors first):\n"
                    f"{_format_feed(forum, agent_id)}"
                )
            else:
                tool_content = "(forum unavailable)"
        elif name in FORUM_ACTION_TOOL_NAMES:
            social_actions += 1
            if forum_enabled:
                tool_content = _apply_forum_action(
                    forum=forum, agent_id=agent_id, tick=tick,
                    tool_call=pending, on_forum_action=on_forum_action,
                    activity=activity,
                )
            else:
                tool_content = "(forum unavailable)"
        else:                       # pragma: no cover — guarded by caller
            break

        messages.append(_assistant_tool_call_message(pending))
        messages.append(_tool_result_message(pending, tool_content))

        # --- decide which tools to offer on the next turn ---
        reads_exhausted = read_turns >= MAX_INFO_TURNS
        social_exhausted = social_actions >= K_SOCIAL
        # On the very last allowed overall turn, force convergence by
        # dropping ALL non-terminating tools.
        last_overall = total_turns >= hard_cap - 1
        next_tools = []
        for t in trade_tools:
            tname = t.get("function", {}).get("name", "")
            is_read = tname in {INFO_TOOL_NAME, FORUM_READ_TOOL_NAME}
            is_social_action = tname in FORUM_ACTION_TOOL_NAMES
            if last_overall and (is_read or is_social_action):
                continue
            if is_read and reads_exhausted:
                continue
            if is_social_action and social_exhausted:
                continue
            next_tools.append(t)

        result = call_with_retry(
            continue_fn,
            max_attempts=max_attempts,
            **base_call_kwargs,
            messages=messages,
            tools=next_tools,
            tool_choice="auto",
        )
        pending = None if last_overall else _read_or_social_call(result)

    return result, activity


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
    forum=None,
    agent_id: Optional[int] = None,
    tick: int = 0,
    forum_enabled: bool = True,
    on_forum_action: Optional[ForumActionCallback] = None,
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

    Forum (social) layer: when `forum_enabled` and the forum tools are among
    `tools` AND a `forum`/`agent_id` are supplied, the SAME bounded
    trade-stage loop also handles `read_forum` (feeds the agent's feed back)
    and the record actions `post_to_forum` / `comment_on_post` /
    `follow_user` (applied to `forum`, capped at `K_SOCIAL` per tick). These
    social tools never terminate the decision; the agent still converges to
    a trade or HOLD. `on_forum_action(kind, payload)` is called for each
    applied action so the runner can emit forum_* events. The forum
    *mechanism* is deterministic; the post/comment text is LLM-generated and
    therefore not bit-for-bit reproducible (the events log it instead).
    """
    if tools is None:
        tools = TOOL_SCHEMAS
    belief_tools, trade_tools = _split_belief_and_trade_tools(tools)
    info_in_tools = any(_tool_name(t) == INFO_TOOL_NAME for t in trade_tools)
    use_info = info_enabled and info_in_tools
    forum_in_tools = any(
        _tool_name(t) in FORUM_TOOL_NAMES for t in trade_tools
    )
    use_forum = (
        forum_enabled and forum_in_tools
        and forum is not None and agent_id is not None
    )
    # The bounded trade-stage loop runs if EITHER the info read-tool or the
    # forum tools are active. When neither is active we keep the single-call
    # fast path (and strip those tools so the LLM can't call them).
    use_loop = use_info or use_forum
    # Forum args passed into the loop only when the forum is actually active,
    # so info-only runs behave exactly as before.
    _forum = forum if use_forum else None
    _forum_agent_id = agent_id if use_forum else None

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
    forum_activity = None
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
                    if use_loop:
                        trade_result, forum_activity = _run_trade_stage_loop(
                            call_fn=call_fn,
                            continue_fn=continue_fn,
                            base_call_kwargs=base_call_kwargs,
                            max_attempts=max_attempts,
                            system_prompt=system_prompt,
                            trade_user_prompt=trade_user_prompt,
                            trade_tools=_drop_loop_tools(
                                trade_tools, info=not use_info,
                                forum=not use_forum,
                            ),
                            tick_size=tick_size,
                            use_info=use_info,
                            search_backend=search_backend,
                            on_info_query=on_info_query,
                            forum=_forum,
                            agent_id=_forum_agent_id,
                            tick=tick,
                            on_forum_action=on_forum_action,
                        )
                    else:
                        # No loop: strip ALL non-terminating tools so the
                        # LLM converges in a single call.
                        trade_tools_eff = _drop_loop_tools(
                            trade_tools, info=True, forum=True,
                        )
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
            if use_loop:
                # No belief stage: run the bounded loop directly on the full
                # tool set (belief tool already absent here).
                result, forum_activity = _run_trade_stage_loop(
                    call_fn=call_fn,
                    continue_fn=continue_fn,
                    base_call_kwargs=base_call_kwargs,
                    max_attempts=max_attempts,
                    system_prompt=system_prompt,
                    trade_user_prompt=user_prompt,
                    trade_tools=_drop_loop_tools(
                        tools, info=not use_info, forum=not use_forum,
                    ),
                    tick_size=tick_size,
                    use_info=use_info,
                    search_backend=search_backend,
                    on_info_query=on_info_query,
                    forum=_forum,
                    agent_id=_forum_agent_id,
                    tick=tick,
                    on_forum_action=on_forum_action,
                )
            else:
                tools_eff = _drop_loop_tools(tools, info=True, forum=True)
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
        forum_activity=forum_activity,
    )
