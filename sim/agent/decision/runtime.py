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
import signal
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


class _DecisionTimeout(Exception):
    """Raised when decide() exceeds its hard wall-clock timeout."""


class _TimeoutGuard:
    """Hard timeout guard using SIGALRM (Unix main-thread only).

    The LLM calls inside decide() are blocking; without a signal-based
    timeout a stuck provider can freeze the whole experiment tick. This
    guard raises _DecisionTimeout after `seconds` wall-clock seconds so
    decide() can return a HOLD with timeout_exceeded=True instead of
    hanging forever.
    """

    def __init__(self, seconds: float):
        self.seconds = seconds
        self._old_handler = None

    def __enter__(self):
        if self.seconds <= 0:
            return self
        # Only install in the main thread of the main interpreter.
        try:
            self._old_handler = signal.signal(
                signal.SIGALRM, self._handler,
            )
            signal.setitimer(signal.ITIMER_REAL, self.seconds)
        except (ValueError, AttributeError):
            # Not in main thread or signal not available (e.g. Windows);
            # fall back to no hard timeout.
            self._old_handler = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._old_handler is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, self._old_handler)
        return False

    @staticmethod
    def _handler(signum, frame):  # noqa: ARG001
        raise _DecisionTimeout(f"decide() exceeded hard timeout")


# Max web-search (get_information) round-trips per tick. Bounds the
# information-gathering part of the loop.
MAX_INFO_TURNS = 2

# Max read_forum round-trips per tick. A SEPARATE budget from web search so a
# search-heavy agent does not starve forum reading — without this they share
# one budget and agents never see the forum, hence never comment/follow.
MAX_FORUM_READ_TURNS = 2

# Max number of *record* social actions (post_to_forum / comment_on_post /
# follow_user) an agent may take per tick. Prevents an agent from spamming
# the forum or looping forever on social actions. The loop also has a hard
# overall turn cap (MAX_INFO_TURNS + MAX_FORUM_READ_TURNS + K_SOCIAL + 1) as a
# final safety bound.
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


def _assistant_tool_call_message(
    tool_call: dict, reasoning_content: str | None = None,
) -> dict:
    """Build the assistant message that records a single tool call, in the
    OpenAI/litellm wire format, so it can be appended to `messages` and
    paired with the matching `role: "tool"` result message.

    When the turn was produced in DeepSeek thinking mode, its
    ``reasoning_content`` MUST be echoed back or the next call fails with
    "The reasoning_content in the thinking mode must be passed back to the
    API". We include it whenever present (harmless for non-thinking models)."""
    msg: dict = {
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
    if reasoning_content:
        msg["reasoning_content"] = reasoning_content
    return msg


def _tool_result_message(tool_call: dict, content: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call.get("id") or "call_get_information",
        "name": tool_call.get("name", ""),
        "content": content,
    }


def _assistant_tool_calls_message(
    tool_calls: list[dict], reasoning_content: str | None = None,
) -> dict:
    """Build one assistant message recording SEVERAL tool calls in the
    OpenAI/litellm wire format. The model may emit several tool calls in a
    single turn (parallel tool calling); each must be echoed back here and
    answered by a matching ``role: "tool"`` message. See
    :func:`_assistant_tool_call_message` for the reasoning_content note."""
    msg: dict = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": tc.get("id") or f"call_{i}",
            "type": "function",
            "function": {
                "name": tc.get("name", ""),
                "arguments": json.dumps(
                    tc.get("arguments") or {}, ensure_ascii=False,
                ),
            },
        } for i, tc in enumerate(tool_calls)],
    }
    if reasoning_content:
        msg["reasoning_content"] = reasoning_content
    return msg


def _is_continuing_call(name: str) -> bool:
    """A tool call that keeps the bounded trade-stage loop going: a read
    (get_information / read_forum) or a forum record action. Any other call
    (a trade tool) is a terminal decision."""
    return name == INFO_TOOL_NAME or name in FORUM_TOOL_NAMES


def _continuing_calls(result: dict) -> list[dict]:
    """All non-terminating tool calls in a result, in the order the model
    emitted them. Empty when the model returned a trade tool / no tool (a
    terminal turn). The model can emit several in one turn, so we process
    them all rather than just the first."""
    return [tc for tc in _tool_calls(result)
            if _is_continuing_call(str(tc.get("name", "")))]


def _read_or_social_call(result: dict) -> dict | None:
    """Return the first non-terminating tool call, or None. Retained for
    callers/tests that only need to know whether the loop should continue."""
    calls = _continuing_calls(result)
    return calls[0] if calls else None


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
    asked to continue. The loop is bounded by separate per-tick limits so it
    always converges to a trade tool or HOLD:
      * at most `MAX_INFO_TURNS` web-search round trips,
      * at most `MAX_FORUM_READ_TURNS` forum-read round trips (separate budget
        so search-heavy agents can still read the forum),
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

    if not _continuing_calls(result):
        return result, activity

    # Enter the multi-turn loop: rebuild the conversation as explicit
    # messages so we can append assistant tool_calls + tool results.
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": trade_user_prompt},
    ]

    info_turns = 0      # get_information (web search)
    forum_read_turns = 0  # read_forum
    social_actions = 0  # post / comment / follow
    # Hard overall cap so a misbehaving model cannot loop forever even if
    # it alternates between the budgets.
    hard_cap = MAX_INFO_TURNS + MAX_FORUM_READ_TURNS + K_SOCIAL + 1
    total_turns = 0

    def _tool_content_for(name: str, call: dict) -> str:
        """Run one continuing tool call and return the text fed back to the
        LLM. Mutates `activity`/`forum` for forum actions/reads."""
        args = call.get("arguments") or {}
        if name == INFO_TOOL_NAME:
            query = str(args.get("query", "")).strip()
            results = search_web(query, backend=search_backend, max_results=5)
            if on_info_query is not None:
                try:
                    on_info_query(query, results)
                except Exception:        # noqa: BLE001
                    pass
            return (
                f"Web search results for \"{query}\":\n"
                f"{_format_search_results(results)}"
            )
        if name == FORUM_READ_TOOL_NAME:
            if not forum_enabled:
                return "(forum unavailable)"
            topic = str(args.get("topic", "")).strip()
            hint = f" (topic: {topic})" if topic else ""
            feed = forum.get_feed_for(agent_id)
            followed = forum.followed_by(agent_id)
            # Record what was read into social memory (newest posts the agent
            # saw), flagging followed authors for priority.
            for p in feed:
                activity["reads"].append({
                    "tick": p.tick, "post_id": p.id,
                    "author_id": p.author_id, "content": p.content,
                    "followed": p.author_id in followed,
                })
            return (
                f"Your forum feed{hint} (followed authors first):\n"
                f"{_format_feed(forum, agent_id)}"
            )
        if name in FORUM_ACTION_TOOL_NAMES:
            if not forum_enabled:
                return "(forum unavailable)"
            return _apply_forum_action(
                forum=forum, agent_id=agent_id, tick=tick,
                tool_call=call, on_forum_action=on_forum_action,
                activity=activity,
            )
        return f"unknown_tool:{name}"

    while total_turns < hard_cap:
        # The model may emit SEVERAL continuing tool calls in one turn
        # (parallel tool calling). Process them all this turn: append the
        # assistant message listing every call (with its reasoning_content),
        # then a tool result for each — required by the OpenAI/DeepSeek wire
        # protocol (every tool_call must be answered).
        calls = _continuing_calls(result)
        if not calls:
            break
        total_turns += 1

        messages.append(_assistant_tool_calls_message(
            calls, result.get("reasoning_content")))
        for call in calls:
            name = str(call.get("name", ""))
            if name == INFO_TOOL_NAME:
                info_turns += 1
            elif name == FORUM_READ_TOOL_NAME:
                forum_read_turns += 1
            elif name in FORUM_ACTION_TOOL_NAMES:
                social_actions += 1
            messages.append(
                _tool_result_message(call, _tool_content_for(name, call)))

        # --- decide which tools to offer on the next turn ---
        # Web search and forum reading have SEPARATE budgets so a
        # search-heavy agent can still read the forum (and then comment/follow).
        info_exhausted = info_turns >= MAX_INFO_TURNS
        forum_read_exhausted = forum_read_turns >= MAX_FORUM_READ_TURNS
        social_exhausted = social_actions >= K_SOCIAL
        # On the very last allowed overall turn, force convergence by
        # dropping ALL non-terminating tools.
        last_overall = total_turns >= hard_cap - 1
        next_tools = []
        for t in trade_tools:
            tname = t.get("function", {}).get("name", "")
            is_info = tname == INFO_TOOL_NAME
            is_forum_read = tname == FORUM_READ_TOOL_NAME
            is_social_action = tname in FORUM_ACTION_TOOL_NAMES
            if last_overall and (is_info or is_forum_read or is_social_action):
                continue
            if is_info and info_exhausted:
                continue
            if is_forum_read and forum_read_exhausted:
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
        if last_overall:
            break

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
        info_enabled=use_info, forum_enabled=use_forum,
    )
    user_prompt = build_user_prompt(
        market, agent, prompt_language=prompt_language,
        forum_enabled=use_forum,
    )

    started = time.time()
    raw = ""
    api_error = ""
    timeout_exceeded = False
    prompt_tokens = 0
    completion_tokens = 0
    parsed = {
        "order_type": "HOLD", "outcome": "YES", "side": "BUY",
        "price": 0.5, "size_usd": 0.0, "reasoning": "",
    }
    belief_update = None
    forum_activity = None
    try:
        with _TimeoutGuard(timeout):
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
                prompt_tokens += belief_result.get("prompt_tokens", 0)
                completion_tokens += belief_result.get("completion_tokens", 0)
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
                        prompt_tokens += trade_result.get("prompt_tokens", 0)
                        completion_tokens += trade_result.get("completion_tokens", 0)
                        raw = _stage_raw(
                            belief_stage=belief_result,
                            trade_stage=trade_result,
                        )
                        parsed = parse_tool_call(
                            trade_result.get("tool_call"), tick_size=tick_size,
                        )
                        # Surface the trade-stage reasoning for display: prefer the
                        # thinking-mode chain-of-thought, then any prose in `text`
                        # (e.g. tool_choice=auto and it declined to call).
                        if not parsed["reasoning"]:
                            parsed["reasoning"] = (
                                trade_result.get("reasoning_content")
                                or trade_result.get("text", "")
                            )[:600]
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
                prompt_tokens += result.get("prompt_tokens", 0)
                completion_tokens += result.get("completion_tokens", 0)
                raw = result.get("raw", "")
                parsed = parse_tool_call(result.get("tool_call"), tick_size=tick_size)
                # Back-compat path for configs that disable the explicit
                # two-stage belief tool.
                if parsed["order_type"] != "UPDATE_BELIEF":
                    belief_update = _parse_belief_result(result)
                else:
                    belief_update = parsed.get("belief_update")
                if not parsed["reasoning"]:
                    parsed["reasoning"] = (
                        result.get("reasoning_content") or result.get("text", "")
                    )[:600]
    except _DecisionTimeout as exc:
        api_error = f"timeout: {exc}"
        timeout_exceeded = True
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
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        timeout_exceeded=timeout_exceeded,
    )
