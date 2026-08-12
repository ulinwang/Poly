from agent.loop import (
    AgentLoopContext,
    AgentLoopEvent,
    AgentLoopEventKind,
    AgentLoopStage,
)
from evaluation.agent_loop.observer import AgentLoopEvaluationObserver


def test_observer_records_identity_and_drops_content():
    observer = AgentLoopEvaluationObserver()
    context = AgentLoopContext.create(run_id="run", tick=2, agent_id=7)
    observer.on_event(AgentLoopEvent(
        kind=AgentLoopEventKind.TOOL_STARTED,
        context=context.step(AgentLoopStage.TOOL, 3),
        sequence=4,
        payload={
            "name": "read_forum",
            "call_id": "call-1",
            "arguments": {"topic": "private"},
            "content": "private",
        },
    ))

    records = observer.pop(context.decision_id)
    assert records == [{
        "kind": "tool_started",
        "stage": "tool",
        "iteration": 3,
        "step_id": f"{context.decision_id}:tool:3",
        "sequence": 4,
        "payload": {"name": "read_forum", "call_id": "call-1"},
    }]
    assert observer.pop(context.decision_id) == []
