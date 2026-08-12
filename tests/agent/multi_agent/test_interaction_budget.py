from __future__ import annotations

from agent.decision.runtime import decide
from agent.decision.tool_schemas import FORUM_TOOL_NAMES, select_tools
from agent.decision.types import AgentSnapshot, MarketSnapshot
from agent.multi_agent.protocol import InteractionBudget
from agent.loop import AgentLoopEventKind
from agent.personas.persona import Persona
from environment.forum import Forum


def _persona() -> Persona:
    return Persona(
        persona_type="Calibrated",
        risk_aversion=0.5,
        capital_initial=100.0,
        profile_text="social trader",
    )


def _market() -> MarketSnapshot:
    return MarketSnapshot(
        yes_best_bid=0.4,
        yes_best_ask=0.5,
        yes_mid=0.45,
        no_best_bid=0.5,
        no_best_ask=0.6,
        no_mid=0.55,
        yes_mid_history=[0.45],
        ticks_remaining=5,
        total_ticks=10,
    )


def _agent() -> AgentSnapshot:
    return AgentSnapshot(1, 100.0, 0.0, 0.0, 0)


def _belief() -> dict:
    call = {
        "id": "belief",
        "name": "update_belief",
        "arguments": {
            "yes_prob": 0.55,
            "confidence": 0.6,
            "rationale": "test",
        },
    }
    return {
        "tool_call": call,
        "tool_calls": [call],
        "text": "",
        "raw": "{}",
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }


def _trade() -> dict:
    call = {
        "id": "trade",
        "name": "place_market_order",
        "arguments": {"outcome": "YES", "side": "BUY", "size_usd": 5},
    }
    return {
        "tool_call": call,
        "tool_calls": [call],
        "text": "",
        "raw": "{}",
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }


def test_explicit_budget_drops_exhausted_interaction_tools():
    forum = Forum()
    forum.post(0, "existing evidence", tick=0)
    interactions: list[str] = []
    continuation_tool_names: list[set[str]] = []

    def initial(**kwargs):
        names = {tool["function"]["name"] for tool in kwargs["tools"]}
        if names == {"update_belief"}:
            return _belief()
        calls = [
            {"id": "read", "name": "read_forum", "arguments": {}},
            {
                "id": "post",
                "name": "post_to_forum",
                "arguments": {"content": "my conclusion"},
            },
        ]
        return {
            "tool_call": calls[0],
            "tool_calls": calls,
            "text": "",
            "raw": "{}",
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

    def continuation(**kwargs):
        names = {tool["function"]["name"] for tool in kwargs["tools"]}
        continuation_tool_names.append(names)
        return _trade()

    decision = decide(
        persona=_persona(),
        question="Q?",
        description="R",
        end_date="2027",
        market=_market(),
        agent=_agent(),
        api_key="unused",
        base_url="",
        model="mock",
        call_fn=initial,
        continue_fn=continuation,
        tools=select_tools(info_enabled=False, forum_enabled=True),
        info_enabled=False,
        forum_enabled=True,
        forum=forum,
        agent_id=1,
        tick=1,
        on_forum_action=lambda kind, payload: interactions.append(kind),
        interaction_budget=InteractionBudget(
            max_forum_reads=1,
            max_social_actions=1,
        ),
        max_attempts=1,
    )

    assert decision.order_type == "MARKET"
    assert interactions == ["read", "post"]
    assert len(forum.posts) == 2
    assert len(continuation_tool_names) == 1
    assert not (continuation_tool_names[0] & set(FORUM_TOOL_NAMES))


def test_zero_budget_never_offers_forum_tools():
    seen_trade_tools: list[set[str]] = []

    def llm(**kwargs):
        names = {tool["function"]["name"] for tool in kwargs["tools"]}
        if names == {"update_belief"}:
            return _belief()
        seen_trade_tools.append(names)
        return _trade()

    decision = decide(
        persona=_persona(),
        question="Q?",
        description="R",
        end_date="2027",
        market=_market(),
        agent=_agent(),
        api_key="unused",
        base_url="",
        model="mock",
        call_fn=llm,
        tools=select_tools(info_enabled=False, forum_enabled=True),
        info_enabled=False,
        forum_enabled=True,
        forum=Forum(),
        agent_id=1,
        interaction_budget=InteractionBudget(
            max_forum_reads=0,
            max_social_actions=0,
        ),
        max_attempts=1,
    )

    assert decision.order_type == "MARKET"
    assert len(seen_trade_tools) == 1
    assert not (seen_trade_tools[0] & set(FORUM_TOOL_NAMES))


def test_parallel_tool_batch_cannot_overshoot_interaction_budgets():
    forum = Forum()
    forum.post(0, "existing evidence", tick=0)
    interactions: list[str] = []
    events = []

    class Observer:
        def on_event(self, event):
            events.append(event)

    def initial(**kwargs):
        names = {tool["function"]["name"] for tool in kwargs["tools"]}
        if names == {"update_belief"}:
            return _belief()
        calls = [
            {"id": "read-1", "name": "read_forum", "arguments": {}},
            {"id": "read-2", "name": "read_forum", "arguments": {}},
            {"id": "post-1", "name": "post_to_forum",
             "arguments": {"content": "first"}},
            {"id": "post-2", "name": "post_to_forum",
             "arguments": {"content": "second"}},
        ]
        return {
            "tool_call": calls[0], "tool_calls": calls, "text": "", "raw": "{}",
            "prompt_tokens": 0, "completion_tokens": 0,
        }

    decision = decide(
        persona=_persona(), question="Q?", description="R", end_date="2027",
        market=_market(), agent=_agent(), api_key="unused", base_url="",
        model="mock", call_fn=initial, continue_fn=lambda **kwargs: _trade(),
        tools=select_tools(info_enabled=False, forum_enabled=True),
        info_enabled=False, forum_enabled=True, forum=forum, agent_id=1, tick=1,
        on_forum_action=lambda kind, payload: interactions.append(kind),
        interaction_budget=InteractionBudget(
            max_forum_reads=1, max_social_actions=1,
        ),
        observer=Observer(), max_attempts=1,
    )

    assert decision.order_type == "MARKET"
    assert interactions == ["read", "post"]
    assert len(forum.posts) == 2
    completions = [
        event for event in events
        if event.kind == AgentLoopEventKind.TOOL_COMPLETED
    ]
    assert [event.payload["status"] for event in completions] == [
        "ok", "budget_exhausted", "ok", "budget_exhausted",
    ]
