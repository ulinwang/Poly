"""Immutable identity and event types for the agent loop."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class AgentLoopStage(str, Enum):
    """Coarse lifecycle stages shared by tracing and evaluation adapters."""

    PROMPT = "prompt"
    BELIEF = "belief"
    TRADE = "trade"
    TOOL = "tool"
    PARSE = "parse"
    EVALUATE = "evaluate"
    FINISH = "finish"


class AgentLoopEventKind(str, Enum):
    """Backend-neutral events emitted during one decision."""

    LOOP_STARTED = "loop_started"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    GENERATION_STARTED = "generation_started"
    GENERATION_COMPLETED = "generation_completed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    LOOP_FAILED = "loop_failed"
    LOOP_COMPLETED = "loop_completed"


@dataclass(frozen=True)
class AgentLoopContext:
    """Stable identity for one agent decision within an experiment run."""

    run_id: str
    tick: int
    agent_id: int
    decision_id: str

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        tick: int,
        agent_id: int,
        decision_id: str | None = None,
    ) -> "AgentLoopContext":
        run = str(run_id or "standalone")
        resolved_id = decision_id or f"{run}:tick:{int(tick)}:agent:{int(agent_id)}"
        return cls(
            run_id=run,
            tick=int(tick),
            agent_id=int(agent_id),
            decision_id=resolved_id,
        )

    def step(self, stage: AgentLoopStage, iteration: int = 0) -> "AgentStepContext":
        return AgentStepContext(
            loop=self,
            stage=stage,
            iteration=int(iteration),
            step_id=f"{self.decision_id}:{stage.value}:{int(iteration)}",
        )


@dataclass(frozen=True)
class AgentStepContext:
    """Stable identity for one stage/iteration inside a decision loop."""

    loop: AgentLoopContext
    stage: AgentLoopStage
    iteration: int
    step_id: str


@dataclass(frozen=True)
class AgentLoopEvent:
    """One ordered lifecycle event delivered to observers."""

    kind: AgentLoopEventKind
    context: AgentStepContext
    sequence: int
    payload: Mapping[str, Any] = field(default_factory=dict)
