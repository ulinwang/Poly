"""Fail-open observer plumbing for agent-loop lifecycle events."""
from __future__ import annotations

import logging
from typing import Any, Iterable, Protocol

from agent.loop.context import (
    AgentLoopContext,
    AgentLoopEvent,
    AgentLoopEventKind,
    AgentLoopStage,
)


log = logging.getLogger(__name__)


class AgentLoopObserver(Protocol):
    """Observer contract implemented by tracing and evaluation adapters."""

    def on_event(self, event: AgentLoopEvent) -> None:
        """Handle one lifecycle event."""


class NoOpAgentLoopObserver:
    """Default observer; intentionally has no side effects."""

    def on_event(self, event: AgentLoopEvent) -> None:  # noqa: ARG002
        return


class CompositeAgentLoopObserver:
    """Fan out events while isolating failures in each child observer."""

    def __init__(self, observers: Iterable[AgentLoopObserver]):
        self._observers = tuple(observers)

    def on_event(self, event: AgentLoopEvent) -> None:
        for observer in self._observers:
            try:
                observer.on_event(event)
            except Exception:  # noqa: BLE001 - telemetry must fail open
                log.debug("agent loop observer failed", exc_info=True)


class AgentLoopEmitter:
    """Assign ordered sequence numbers and safely deliver lifecycle events."""

    def __init__(
        self,
        context: AgentLoopContext,
        observer: AgentLoopObserver | None = None,
    ) -> None:
        self.context = context
        self._observer = observer or NoOpAgentLoopObserver()
        self._sequence = 0

    def emit(
        self,
        kind: AgentLoopEventKind,
        stage: AgentLoopStage,
        *,
        iteration: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> AgentLoopEvent:
        event = AgentLoopEvent(
            kind=kind,
            context=self.context.step(stage, iteration),
            sequence=self._sequence,
            payload=dict(payload or {}),
        )
        self._sequence += 1
        try:
            self._observer.on_event(event)
        except Exception:  # noqa: BLE001 - simulation behavior wins over hooks
            log.debug("agent loop observer failed", exc_info=True)
        return event
