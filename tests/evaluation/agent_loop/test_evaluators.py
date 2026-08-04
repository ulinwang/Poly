from __future__ import annotations

from agent.decision import Decision
from agent.multi_agent.protocol import (
    InteractionBudget,
    InteractionDelivery,
    InteractionKind,
    InteractionTranscript,
    InteractionVisibility,
)
from evaluation.agent_loop.evaluators import evaluate_decision, evaluate_multi_agent


def _decision(**overrides) -> Decision:
    values = {
        "order_type": "LIMIT",
        "outcome": "YES",
        "side": "BUY",
        "price": 0.51,
        "size_usd": 10.0,
        "reasoning": "fixed",
        "raw_response": "fixed",
        "api_latency_ms": 4,
        "api_error": "",
        "belief_update": {"yes_prob": 0.6, "confidence": 0.8, "rationale": "x"},
        "decision_id": "run:tick:1:agent:2",
        "prompt_metadata": [{
            "source": "local", "name": "trade", "version": "1",
            "content_hash": "abc123", "language": "en",
        }],
    }
    values.update(overrides)
    return Decision(**values)


def _lifecycle(*, tool_completed: bool = True):
    events = [
        {"kind": "loop_started", "sequence": 0, "payload": {}},
        {"kind": "tool_started", "sequence": 1,
         "payload": {"name": "read_forum", "call_id": "call-1"}},
    ]
    if tool_completed:
        events.append({
            "kind": "tool_completed", "sequence": 2,
            "payload": {"name": "read_forum", "call_id": "call-1", "status": "ok"},
        })
    events.append({
        "kind": "loop_completed", "sequence": len(events),
        "payload": {"status": "ok"},
    })
    return events


def test_decision_evaluators_are_deterministic_and_catch_invalid_action():
    kwargs = dict(
        run_id="run", tick=1, agent_id=2, tick_size=0.01,
        model="mock-model", lifecycle_events=_lifecycle(),
    )
    first = evaluate_decision(_decision(), **kwargs)
    second = evaluate_decision(_decision(), **kwargs)
    assert [score.to_record() for score in first] == [score.to_record() for score in second]
    assert all(score.passed for score in first)

    invalid = evaluate_decision(
        _decision(order_type="HOLD", size_usd=5.0), **kwargs,
    )
    by_name = {score.name: score for score in invalid}
    assert not by_name["decision.action_valid"].passed
    assert by_name["decision.action_valid"].hard
    assert all(score.step_id == "run:tick:1:agent:2:evaluate:0"
               for score in first)
    assert all(score.model == "mock-model" for score in first)
    assert all(score.prompt_versions == ("trade@1:abc123",) for score in first)


def test_lifecycle_evaluator_rejects_unpaired_tool_transcript():
    scores = evaluate_decision(
        _decision(), run_id="run", tick=1, agent_id=2,
        lifecycle_events=_lifecycle(tool_completed=False),
    )
    by_name = {score.name: score for score in scores}
    assert not by_name["decision.lifecycle_valid"].passed
    assert not by_name["decision.budget_compliance"].passed


def test_tool_budget_counts_fixed_information_transcript():
    events = [{"kind": "loop_started", "sequence": 0, "payload": {}}]
    for index in range(3):
        events.extend([
            {"kind": "tool_started", "sequence": len(events),
             "payload": {"name": "get_information", "call_id": f"info-{index}"}},
            {"kind": "tool_completed", "sequence": len(events) + 1,
             "payload": {"name": "get_information", "call_id": f"info-{index}"}},
        ])
    events.append({
        "kind": "loop_completed", "sequence": len(events), "payload": {},
    })
    scores = evaluate_decision(
        _decision(), run_id="run", tick=1, agent_id=2,
        lifecycle_events=events,
    )
    budget = next(score for score in scores
                  if score.name == "decision.budget_compliance")
    assert not budget.passed
    assert budget.details["information_calls"] == 3


def test_budget_exhaustion_is_compliant_only_when_decision_is_hold():
    kwargs = dict(
        run_id="run", tick=1, agent_id=2, token_budget=100, total_tokens=100,
        lifecycle_events=_lifecycle(),
    )
    trade = {score.name: score for score in evaluate_decision(_decision(), **kwargs)}
    hold = {score.name: score for score in evaluate_decision(
        _decision(order_type="HOLD", size_usd=0.0), **kwargs,
    )}
    assert not trade["decision.budget_compliance"].passed
    assert hold["decision.budget_compliance"].passed


def test_all_engine_terminal_action_shapes_are_supported():
    cases = [
        _decision(order_type="CANCEL", price=0.0, size_usd=0.0),
        _decision(order_type="SPLIT", price=0.0, size_usd=5.0),
        _decision(order_type="MERGE", price=0.0, size_usd=5.0),
        _decision(order_type="UPDATE_BELIEF", price=0.6, size_usd=0.0),
    ]
    for decision in cases:
        scores = evaluate_decision(
            decision, run_id="run", tick=1, agent_id=2,
            lifecycle_events=_lifecycle(),
        )
        by_name = {score.name: score for score in scores}
        assert by_name["decision.schema_valid"].passed
        assert by_name["decision.action_valid"].passed


def test_multi_agent_protocol_scores_order_delivery_budget_and_participation():
    transcript = InteractionTranscript()
    post = transcript.append(
        run_id="run", tick=0, channel="forum", kind=InteractionKind.POST,
        sender_id=0,
        delivery=InteractionDelivery(InteractionVisibility.PUBLIC, (0, 1), 0),
        source_ref="forum:post:0", correlation_id="forum:post:0",
    )
    transcript.append(
        run_id="run", tick=0, channel="forum", kind=InteractionKind.READ,
        sender_id=post.sender_id,
        delivery=InteractionDelivery(InteractionVisibility.DIRECT, (1,), 0),
        source_ref=post.source_ref, correlation_id=post.source_ref,
        metadata={"reader_id": 1, "read_batch_id": "read-1"},
    )
    scores = evaluate_multi_agent(
        transcript.messages,
        run_id="run",
        expected_agent_ids=(0, 1),
        schedules=({"tick": 0, "decision_order": [0, 1]},),
        interaction_budget=InteractionBudget(max_forum_reads=1, max_social_actions=1),
    )
    assert all(score.passed for score in scores)
    assert next(score for score in scores if score.name == "multi_agent.participation").value == 1.0
