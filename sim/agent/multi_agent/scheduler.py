"""Deterministic decision scheduling independent from Agent Loop internals."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass(frozen=True)
class TickSchedule:
    tick: int
    decision_order: tuple[int, ...]
    scheduler: str


class AgentScheduler(Protocol):
    def schedule(self, *, tick: int, agent_ids: tuple[int, ...]) -> TickSchedule:
        """Return the decision-call order for one tick."""


class SequentialAgentScheduler:
    """Preserve the agent order supplied by the environment observer."""

    name = "sequential"

    def schedule(self, *, tick: int, agent_ids: tuple[int, ...]) -> TickSchedule:
        return TickSchedule(
            tick=int(tick),
            decision_order=tuple(int(agent_id) for agent_id in agent_ids),
            scheduler=self.name,
        )


def validate_schedule(
    schedule: TickSchedule,
    expected_agent_ids: Iterable[int],
    *,
    expected_tick: int | None = None,
) -> TickSchedule:
    """Reject duplicate, missing, unknown, or wrong-tick scheduler output."""
    expected = tuple(int(agent_id) for agent_id in expected_agent_ids)
    actual = tuple(int(agent_id) for agent_id in schedule.decision_order)
    if schedule.tick < 0:
        raise ValueError("schedule tick must be non-negative")
    if expected_tick is not None and schedule.tick != int(expected_tick):
        raise ValueError("schedule tick does not match the requested tick")
    if len(actual) != len(set(actual)):
        raise ValueError("schedule contains duplicate agent ids")
    if set(actual) != set(expected) or len(actual) != len(expected):
        raise ValueError("schedule must contain every agent exactly once")
    return schedule
