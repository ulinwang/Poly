"""Provider-free evaluators for live decisions and replayed transcripts."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from agent.decision import Decision
from agent.multi_agent.protocol import (
    InteractionBudget,
    InteractionKind,
    InteractionMessage,
)
from evaluation.agent_loop.schema import EvaluationScore


_ORDER_TYPES = frozenset({"HOLD", "MARKET", "LIMIT"})
_OUTCOMES = frozenset({"YES", "NO"})
_SIDES = frozenset({"BUY", "SELL"})


def _score(
    name: str,
    passed: bool,
    *,
    hard: bool,
    scope: str,
    run_id: str,
    decision_id: str = "",
    tick: int | None = None,
    agent_id: int | None = None,
    value: float | None = None,
    details: Mapping[str, Any] | None = None,
) -> EvaluationScore:
    return EvaluationScore(
        name=name,
        value=float(passed if value is None else value),
        passed=bool(passed),
        hard=hard,
        scope=scope,  # type: ignore[arg-type]
        run_id=str(run_id),
        decision_id=str(decision_id),
        tick=tick,
        agent_id=agent_id,
        details=dict(details or {}),
    )


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def evaluate_decision(
    decision: Decision,
    *,
    run_id: str,
    tick: int,
    agent_id: int,
    tick_size: float = 0.01,
    token_budget: int = 0,
    total_tokens: int = 0,
    interaction_budget: InteractionBudget = InteractionBudget(),
) -> list[EvaluationScore]:
    """Evaluate one parsed Decision without another model/provider call."""
    identity = {
        "run_id": run_id,
        "decision_id": decision.decision_id,
        "tick": int(tick),
        "agent_id": int(agent_id),
    }
    schema_valid = (
        decision.order_type in _ORDER_TYPES
        and decision.outcome in _OUTCOMES
        and decision.side in _SIDES
        and _finite_number(decision.price)
        and _finite_number(decision.size_usd)
        and 0.0 <= float(decision.price) <= 1.0
        and float(decision.size_usd) >= 0.0
    )
    action_valid = schema_valid and (
        (decision.order_type == "HOLD" and float(decision.size_usd) == 0.0)
        or (
            decision.order_type == "MARKET"
            and float(decision.size_usd) > 0.0
        )
        or (
            decision.order_type == "LIMIT"
            and float(decision.size_usd) > 0.0
            and float(decision.price) >= float(tick_size)
            and float(decision.price) <= 1.0 - float(tick_size)
        )
    )
    terminal = decision.order_type in _ORDER_TYPES and bool(decision.decision_id)

    activity = decision.forum_activity or {}
    social_count = sum(
        len(activity.get(key) or ()) for key in ("posts", "comments", "follows")
    )
    # ``reads`` contains delivered rows rather than provider turns. Runtime
    # enforcement is authoritative for read-call limits; the evaluator still
    # exposes delivery volume for diagnosis without treating it as a hard cap.
    token_compliant = (
        token_budget <= 0
        or total_tokens < token_budget
        or decision.order_type == "HOLD"
    )
    interaction_compliant = social_count <= interaction_budget.max_social_actions
    budget_compliant = token_compliant and interaction_compliant

    belief = decision.belief_update
    belief_present = belief is not None
    belief_valid = (
        belief is None
        or (
            _finite_number(belief.get("yes_prob"))
            and 0.0 <= float(belief["yes_prob"]) <= 1.0
            and _finite_number(belief.get("confidence"))
            and 0.0 <= float(belief["confidence"]) <= 1.0
        )
    )
    prompt_identity = [
        {
            key: value for key, value in item.items()
            if key not in {"variables"}
        }
        for item in (decision.prompt_metadata or [])
    ]

    return [
        _score("decision.schema_valid", schema_valid, hard=True, scope="decision",
               details={"order_type": decision.order_type}, **identity),
        _score("decision.terminal_convergence", terminal, hard=True,
               scope="decision", details={"api_error": bool(decision.api_error)},
               **identity),
        _score("decision.action_valid", action_valid, hard=True, scope="decision",
               details={"tick_size": tick_size}, **identity),
        _score("decision.budget_compliance", budget_compliant, hard=True,
               scope="decision", details={
                   "token_budget": token_budget,
                   "total_tokens": total_tokens,
                   "social_actions": social_count,
                   "max_social_actions": interaction_budget.max_social_actions,
                   "read_deliveries": len(activity.get("reads") or ()),
               }, **identity),
        _score("decision.belief_valid", belief_valid, hard=True, scope="decision",
               details={"present": belief_present}, **identity),
        _score("decision.belief_present", belief_present, hard=False,
               scope="decision", details={}, **identity),
        _score("decision.prompt_reproducible", bool(prompt_identity), hard=False,
               scope="decision", details={"prompts": prompt_identity}, **identity),
    ]


def evaluate_multi_agent(
    messages: Iterable[InteractionMessage],
    *,
    run_id: str,
    expected_agent_ids: Sequence[int],
    schedules: Sequence[Mapping[str, Any]] = (),
    interaction_budget: InteractionBudget = InteractionBudget(),
) -> list[EvaluationScore]:
    """Evaluate protocol ordering, delivery, budgets and participation."""
    rows = list(messages)
    expected = {int(agent_id) for agent_id in expected_agent_ids}
    sequences = [message.sequence for message in rows]
    monotonic = sequences == sorted(sequences) and len(sequences) == len(set(sequences))

    known_sources: set[str] = set()
    delivery_valid = True
    social_counts: Counter[tuple[int, int]] = Counter()
    read_batches: set[tuple[int, int, str]] = set()
    participants: set[int] = set()
    for message in rows:
        recipients = set(message.delivery.recipient_ids)
        participants.add(message.sender_id)
        participants.update(recipients)
        if (
            message.sender_id not in expected
            or not recipients.issubset(expected)
            or message.delivery.delivered_at_tick < message.tick
        ):
            delivery_valid = False
        if message.kind in {InteractionKind.COMMENT, InteractionKind.READ}:
            if message.correlation_id not in known_sources:
                delivery_valid = False
        if message.kind == InteractionKind.POST:
            known_sources.add(message.source_ref)
        if message.kind in {
            InteractionKind.POST, InteractionKind.COMMENT, InteractionKind.FOLLOW,
        }:
            social_counts[(message.tick, message.sender_id)] += 1
        if message.kind == InteractionKind.READ:
            reader = int(message.metadata.get("reader_id", -1))
            batch = str(message.metadata.get("read_batch_id", message.message_id))
            read_batches.add((message.tick, reader, batch))

    budget_valid = (
        all(count <= interaction_budget.max_social_actions
            for count in social_counts.values())
        and all(
            sum(1 for tick, reader, _ in read_batches if (tick, reader) == key)
            <= interaction_budget.max_forum_reads
            for key in {(tick, reader) for tick, reader, _ in read_batches}
        )
    )
    schedules_valid = all(
        len(order := tuple(int(x) for x in schedule.get("decision_order", ())))
        == len(set(order)) == len(expected)
        and set(order) == expected
        for schedule in schedules
    )
    participation = len(participants & expected) / max(len(expected), 1)

    return [
        _score("multi_agent.sequence_valid", monotonic, hard=True, scope="run",
               run_id=run_id, details={"messages": len(rows)}),
        _score("multi_agent.delivery_valid", delivery_valid, hard=True, scope="run",
               run_id=run_id, details={"known_agents": sorted(expected)}),
        _score("multi_agent.budget_compliance", budget_valid, hard=True, scope="run",
               run_id=run_id, details={
                   "max_forum_reads": interaction_budget.max_forum_reads,
                   "max_social_actions": interaction_budget.max_social_actions,
               }),
        _score("multi_agent.schedule_valid", schedules_valid, hard=True, scope="run",
               run_id=run_id, details={"ticks": len(schedules)}),
        _score("multi_agent.participation", participation > 0.0, hard=False,
               scope="run", run_id=run_id, value=participation,
               details={"participants": sorted(participants & expected),
                        "expected": len(expected)}),
    ]


@dataclass
class AgentEvaluationSession:
    """Stateful run accumulator; local events remain the source of truth."""

    run_id: str
    interaction_budget: InteractionBudget = InteractionBudget()
    schedules: list[dict[str, Any]] = field(default_factory=list)
    beliefs: list[tuple[int, float]] = field(default_factory=list)

    def record_schedule(self, *, tick: int, decision_order: Sequence[int]) -> None:
        self.schedules.append({
            "tick": int(tick),
            "decision_order": [int(agent_id) for agent_id in decision_order],
        })

    def score_decision(self, decision: Decision, **kwargs: Any) -> list[EvaluationScore]:
        belief = decision.belief_update
        if belief is not None and _finite_number(belief.get("yes_prob")):
            self.beliefs.append((int(kwargs["agent_id"]), float(belief["yes_prob"])))
        return evaluate_decision(
            decision,
            run_id=self.run_id,
            interaction_budget=self.interaction_budget,
            **kwargs,
        )

    def score_run(
        self,
        *,
        messages: Iterable[InteractionMessage],
        expected_agent_ids: Sequence[int],
        final_yes: float,
        resolved_yes: int | None,
    ) -> list[EvaluationScore]:
        scores = evaluate_multi_agent(
            messages,
            run_id=self.run_id,
            expected_agent_ids=expected_agent_ids,
            schedules=self.schedules,
            interaction_budget=self.interaction_budget,
        )
        target = float(resolved_yes) if resolved_yes in {0, 1} else float(final_yes)
        if self.beliefs:
            brier = sum((belief - target) ** 2 for _, belief in self.beliefs) / len(self.beliefs)
            value = 1.0 - brier
            scores.append(_score(
                "run.belief_calibration",
                value >= 0.75,
                hard=False,
                scope="run",
                run_id=self.run_id,
                value=value,
                details={"brier": brier, "target": target, "n": len(self.beliefs)},
            ))
        else:
            scores.append(_score(
                "run.belief_calibration",
                False,
                hard=False,
                scope="run",
                run_id=self.run_id,
                value=0.0,
                details={"reason": "no_beliefs", "target": target, "n": 0},
            ))
        return scores
