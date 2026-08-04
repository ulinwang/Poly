from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from agent.decision.runtime import decide
from agent.decision.tool_schemas import select_tools
from agent.decision.types import AgentSnapshot, MarketSnapshot
from agent.info import SearchResult
from agent.loop import (
    AgentLoopContext,
    AgentLoopEventKind,
    AgentLoopStage,
)
from agent.personas.persona import Persona


class RecordingObserver:
    def __init__(self) -> None:
        self.events = []

    def on_event(self, event) -> None:
        self.events.append(event)


def _persona() -> Persona:
    return Persona(
        persona_type="Calibrated",
        risk_aversion=0.5,
        capital_initial=100.0,
        profile_text="a careful trader",
    )


def _market() -> MarketSnapshot:
    return MarketSnapshot(
        yes_best_bid=0.4,
        yes_best_ask=0.5,
        yes_mid=0.45,
        no_best_bid=0.5,
        no_best_ask=0.6,
        no_mid=0.55,
        yes_mid_history=[0.5, 0.47, 0.45],
        ticks_remaining=4,
        total_ticks=10,
    )


def _agent() -> AgentSnapshot:
    return AgentSnapshot(
        agent_id=7,
        cash=100.0,
        yes_shares=0.0,
        no_shares=0.0,
        n_resting_orders=0,
    )


def _belief_call() -> dict:
    call = {
        "id": "belief-1",
        "name": "update_belief",
        "arguments": {
            "yes_prob": 0.6,
            "confidence": 0.7,
            "rationale": "signal exceeds the market",
        },
    }
    return {
        "tool_call": call,
        "tool_calls": [call],
        "text": "",
        "raw": "{}",
        "prompt_tokens": 3,
        "completion_tokens": 2,
    }


def _trade_call() -> dict:
    call = {
        "id": "trade-1",
        "name": "place_market_order",
        "arguments": {"outcome": "YES", "side": "BUY", "size_usd": 10},
    }
    return {
        "tool_call": call,
        "tool_calls": [call],
        "text": "",
        "raw": "{}",
        "prompt_tokens": 4,
        "completion_tokens": 2,
    }


def test_context_and_step_ids_are_stable_and_immutable():
    first = AgentLoopContext.create(run_id="sim-42", tick=3, agent_id=7)
    second = AgentLoopContext.create(run_id="sim-42", tick=3, agent_id=7)

    assert first == second
    assert first.decision_id == "sim-42:tick:3:agent:7"
    assert first.step(AgentLoopStage.TRADE, 2).step_id == (
        "sim-42:tick:3:agent:7:trade:2"
    )
    with pytest.raises(FrozenInstanceError):
        first.tick = 4


def test_two_stage_decision_emits_ordered_lifecycle():
    observer = RecordingObserver()
    context = AgentLoopContext.create(run_id="sim-42", tick=3, agent_id=7)

    def fake_llm(**kwargs):
        names = {tool["function"]["name"] for tool in kwargs["tools"]}
        return _belief_call() if names == {"update_belief"} else _trade_call()

    decision = decide(
        persona=_persona(),
        question="Q?",
        description="R",
        end_date="2027",
        market=_market(),
        agent=_agent(),
        api_key="unused",
        base_url="",
        model="mock-model",
        call_fn=fake_llm,
        max_attempts=1,
        loop_context=context,
        observer=observer,
    )

    assert decision.decision_id == context.decision_id
    assert decision.order_type == "MARKET"
    assert [event.sequence for event in observer.events] == list(
        range(len(observer.events))
    )
    assert observer.events[0].kind == AgentLoopEventKind.LOOP_STARTED
    assert observer.events[-1].kind == AgentLoopEventKind.LOOP_COMPLETED
    generations = [
        event for event in observer.events
        if event.kind == AgentLoopEventKind.GENERATION_COMPLETED
    ]
    assert [event.context.stage for event in generations] == [
        AgentLoopStage.BELIEF,
        AgentLoopStage.TRADE,
    ]
    assert all(event.context.loop == context for event in observer.events)


def test_tool_loop_emits_tool_pair_and_generation_iterations(monkeypatch):
    observer = RecordingObserver()

    def fake_search(query, backend=None, max_results=5):  # noqa: ARG001
        return [SearchResult(title="Result", snippet=query, url="https://example.test")]

    monkeypatch.setattr("agent.decision.runtime.search_web", fake_search)

    def initial(**kwargs):
        names = {tool["function"]["name"] for tool in kwargs["tools"]}
        if names == {"update_belief"}:
            return _belief_call()
        call = {
            "id": "search-1",
            "name": "get_information",
            "arguments": {"query": "latest evidence"},
        }
        return {
            "tool_call": call,
            "tool_calls": [call],
            "text": "",
            "reasoning_content": "private provider reasoning",
            "raw": "{}",
            "prompt_tokens": 1,
            "completion_tokens": 1,
        }

    decision = decide(
        persona=_persona(),
        question="Q?",
        description="R",
        end_date="2027",
        market=_market(),
        agent=_agent(),
        api_key="unused",
        base_url="",
        model="mock-model",
        call_fn=initial,
        continue_fn=lambda **kwargs: _trade_call(),
        tools=select_tools(info_enabled=True, forum_enabled=False),
        info_enabled=True,
        forum_enabled=False,
        max_attempts=1,
        loop_context=AgentLoopContext.create(
            run_id="sim-tool", tick=1, agent_id=7,
        ),
        observer=observer,
    )

    assert decision.order_type == "MARKET"
    tool_events = [
        event for event in observer.events
        if event.kind in {
            AgentLoopEventKind.TOOL_STARTED,
            AgentLoopEventKind.TOOL_COMPLETED,
        }
    ]
    assert [event.kind for event in tool_events] == [
        AgentLoopEventKind.TOOL_STARTED,
        AgentLoopEventKind.TOOL_COMPLETED,
    ]
    trade_starts = [
        event.context.iteration for event in observer.events
        if event.kind == AgentLoopEventKind.GENERATION_STARTED
        and event.context.stage == AgentLoopStage.TRADE
    ]
    assert trade_starts == [0, 1]
    completed_generations = [
        event for event in observer.events
        if event.kind == AgentLoopEventKind.GENERATION_COMPLETED
    ]
    assert all(
        "reasoning_content" not in event.payload
        for event in completed_generations
    )
    continuation = next(
        event for event in observer.events
        if event.kind == AgentLoopEventKind.GENERATION_STARTED
        and event.context.stage == AgentLoopStage.TRADE
        and event.context.iteration == 1
    )
    assert all(
        "reasoning_content" not in message
        for message in continuation.payload["messages"]
    )


def test_observer_failure_does_not_change_decision():
    class BrokenObserver:
        def on_event(self, event):  # noqa: ARG002
            raise RuntimeError("telemetry unavailable")

    def fake_llm(**kwargs):
        names = {tool["function"]["name"] for tool in kwargs["tools"]}
        return _belief_call() if names == {"update_belief"} else _trade_call()

    decision = decide(
        persona=_persona(),
        question="Q?",
        description="R",
        end_date="2027",
        market=_market(),
        agent=_agent(),
        api_key="unused",
        base_url="",
        model="mock-model",
        call_fn=fake_llm,
        max_attempts=1,
        observer=BrokenObserver(),
    )

    assert decision.order_type == "MARKET"
    assert decision.api_error == ""
