"""Content-safe lifecycle recorder used by online and offline evaluation."""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

from agent.loop import AgentLoopEvent


_EVALUATION_PAYLOAD_KEYS = frozenset({
    "call_id",
    "completion_tokens",
    "error_type",
    "handled",
    "has_api_error",
    "has_belief_update",
    "latency_ms",
    "name",
    "order_type",
    "parsed",
    "prompt_tokens",
    "status",
    "target",
    "timeout_exceeded",
    "valid",
})


class AgentLoopEvaluationObserver:
    """Collect minimal lifecycle facts without prompt, output or tool content."""

    def __init__(self) -> None:
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = threading.Lock()

    def on_event(self, event: AgentLoopEvent) -> None:
        kind = getattr(event.kind, "value", event.kind)
        stage = getattr(event.context.stage, "value", event.context.stage)
        payload = {
            str(key): value
            for key, value in event.payload.items()
            if str(key) in _EVALUATION_PAYLOAD_KEYS
            and (value is None or isinstance(value, (bool, int, float, str)))
        }
        record = {
            "kind": str(kind),
            "stage": str(stage),
            "iteration": int(event.context.iteration),
            "step_id": str(event.context.step_id),
            "sequence": int(event.sequence),
            "payload": payload,
        }
        with self._lock:
            self._events[event.context.loop.decision_id].append(record)

    def pop(self, decision_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return self._events.pop(str(decision_id), [])
