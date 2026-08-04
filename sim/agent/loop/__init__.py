"""Stable lifecycle contracts for one agent decision loop.

The decision runtime emits these events without depending on any telemetry
backend.  Observability, evaluation, and replay adapters can subscribe through
``AgentLoopObserver`` while normal simulations use the no-op observer.
"""

from agent.loop.context import (
    AgentLoopContext,
    AgentLoopEvent,
    AgentLoopEventKind,
    AgentLoopStage,
    AgentStepContext,
)
from agent.loop.observer import (
    AgentLoopEmitter,
    AgentLoopObserver,
    CompositeAgentLoopObserver,
    NoOpAgentLoopObserver,
)

__all__ = [
    "AgentLoopContext",
    "AgentLoopEmitter",
    "AgentLoopEvent",
    "AgentLoopEventKind",
    "AgentLoopObserver",
    "AgentLoopStage",
    "AgentStepContext",
    "CompositeAgentLoopObserver",
    "NoOpAgentLoopObserver",
]
