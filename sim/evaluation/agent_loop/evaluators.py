"""Provider-free evaluators for live decisions and replayed transcripts."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from agent.decision import (
    Decision,
    INFO_TOOL_NAME,
    MAX_INFO_TURNS,
    VALID_OUTCOMES,
    VALID_ORDER_TYPES,
    VALID_SIDES,
)
from agent.multi_agent.protocol import (
    InteractionBudget,
    InteractionKind,
    InteractionMessage,
)
from evaluation.agent_loop.schema import EvaluationScore


_ORDER_TYPES = frozenset(VALID_ORDER_TYPES)
_OUTCOMES = frozenset(VALID_OUTCOMES)
_SIDES = frozenset(VALID_SIDES)
_SOCIAL_TOOL_NAMES = frozenset({
    "post_to_forum", "comment_on_post", "follow_user",
})
_FORUM_READ_TOOL_NAME = "read_forum"


def _score(
    name: str,
    passed: bool,
    *,
    hard: bool,
    scope: str,
    run_id: str,
    decision_id: str = "",
    step_id: str = "",
    tick: int | None = None,
    agent_id: int | None = None,
    model: str = "",
    prompt_versions: Sequence[str] = (),
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
        step_id=str(step_id),
        tick=tick,
        agent_id=agent_id,
        model=str(model),
        prompt_versions=tuple(str(item) for item in prompt_versions),
        details=dict(details or {}),
    )


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _public_prompt_identity(decision: Decision) -> list[dict[str, Any]]:
    return [
        {
            key: value for key, value in item.items()
            if key != "variables"
        }
        for item in (decision.prompt_metadata or [])
    ]


def _prompt_versions(identity: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    versions = []
    for item in identity:
        revision = item.get("version") or item.get("label") or "unknown"
        content_hash = str(item.get("content_hash") or "")[:12]
        suffix = f":{content_hash}" if content_hash else ""
        versions.append(f"{item.get('name', 'unknown')}@{revision}{suffix}")
    return tuple(versions)


def _lifecycle_facts(
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    kinds = [str(event.get("kind", "")) for event in events]
    sequences = [int(event.get("sequence", -1)) for event in events]
    monotonic = (
        sequences == sorted(sequences)
        and len(sequences) == len(set(sequences))
        and all(sequence >= 0 for sequence in sequences)
    )
    starts: Counter[str] = Counter()
    completions: Counter[str] = Counter()
    generation_starts: Counter[tuple[str, int]] = Counter()
    generation_completions: Counter[tuple[str, int]] = Counter()
    tool_names: list[str] = []
    for event in events:
        payload = event.get("payload") or {}
        if not isinstance(payload, Mapping):
            continue
        call_id = str(payload.get("call_id") or "")
        if event.get("kind") == "tool_started":
            starts[call_id] += 1
            tool_names.append(str(payload.get("name") or ""))
        elif event.get("kind") == "tool_completed":
            completions[call_id] += 1
        generation_key = (
            str(event.get("stage", "")), int(event.get("iteration", 0)),
        )
        if event.get("kind") == "generation_started":
            generation_starts[generation_key] += 1
        elif event.get("kind") == "generation_completed":
            generation_completions[generation_key] += 1
    paired_tools = starts == completions and all(call_id for call_id in starts)
    paired_generations = generation_starts == generation_completions
    complete_loop = (
        bool(events)
        and kinds[0] == "loop_started"
        and kinds[-1] == "loop_completed"
        and kinds.count("loop_completed") == 1
    )
    return {
        "event_count": len(events),
        "generation_count": kinds.count("generation_started"),
        "tool_count": len(tool_names),
        "tool_names": tool_names,
        "forum_reads": tool_names.count(_FORUM_READ_TOOL_NAME),
        "information_calls": tool_names.count(INFO_TOOL_NAME),
        "social_actions": sum(name in _SOCIAL_TOOL_NAMES for name in tool_names),
        "sequence_valid": monotonic,
        "paired_tools": paired_tools,
        "paired_generations": paired_generations,
        "complete_loop": complete_loop,
    }


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
    lifecycle_events: Sequence[Mapping[str, Any]] = (),
    model: str = "",
) -> list[EvaluationScore]:
    """Evaluate one parsed Decision without another model/provider call."""
    prompt_identity = _public_prompt_identity(decision)
    prompt_versions = _prompt_versions(prompt_identity)
    step_id = f"{decision.decision_id}:evaluate:0" if decision.decision_id else ""
    identity = {
        "run_id": run_id,
        "decision_id": decision.decision_id,
        "step_id": step_id,
        "tick": int(tick),
        "agent_id": int(agent_id),
        "model": model,
        "prompt_versions": prompt_versions,
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
    action_valid = schema_valid and (
        (decision.order_type == "HOLD" and float(decision.size_usd) == 0.0)
        or (
            decision.order_type == "CANCEL"
            and float(decision.size_usd) == 0.0
        )
        or (
            decision.order_type == "UPDATE_BELIEF"
            and float(decision.size_usd) == 0.0
            and belief_present
            and belief_valid
        )
        or (
            decision.order_type in {"MARKET", "SPLIT", "MERGE"}
            and float(decision.size_usd) > 0.0
        )
        or (
            decision.order_type == "LIMIT"
            and float(decision.size_usd) > 0.0
            and float(decision.price) >= float(tick_size)
            and float(decision.price) <= 1.0 - float(tick_size)
        )
    )
    lifecycle = _lifecycle_facts(lifecycle_events)
    has_lifecycle = bool(lifecycle_events)
    terminal = (
        decision.order_type in _ORDER_TYPES
        and bool(decision.decision_id)
        and (lifecycle["complete_loop"] if has_lifecycle else True)
    )
    lifecycle_valid = (
        lifecycle["sequence_valid"]
        and lifecycle["paired_tools"]
        and lifecycle["paired_generations"]
        and lifecycle["complete_loop"]
        if has_lifecycle else terminal and decision.order_type == "HOLD"
    )

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
    observed_social_actions = (
        int(lifecycle["social_actions"]) if has_lifecycle else social_count
    )
    observed_forum_reads = int(lifecycle["forum_reads"]) if has_lifecycle else 0
    interaction_compliant = (
        observed_social_actions <= interaction_budget.max_social_actions
        and observed_forum_reads <= interaction_budget.max_forum_reads
        and int(lifecycle["information_calls"]) <= MAX_INFO_TURNS
        and (bool(lifecycle["paired_tools"]) if has_lifecycle else True)
        and (bool(lifecycle["paired_generations"]) if has_lifecycle else True)
    )
    budget_compliant = token_compliant and interaction_compliant

    prompt_reproducible = bool(prompt_identity) and all(
        item.get("name")
        and (item.get("version") or item.get("label"))
        and item.get("content_hash")
        and item.get("language")
        for item in prompt_identity
    )

    return [
        _score("decision.schema_valid", schema_valid, hard=True, scope="decision",
               details={"order_type": decision.order_type}, **identity),
        _score("decision.terminal_convergence", terminal, hard=True,
               scope="decision", details={
                   "api_error": bool(decision.api_error),
                   "lifecycle_observed": has_lifecycle,
               },
               **identity),
        _score("decision.lifecycle_valid", lifecycle_valid, hard=True,
               scope="decision", details=lifecycle, **identity),
        _score("decision.action_valid", action_valid, hard=True, scope="decision",
               details={"tick_size": tick_size}, **identity),
        _score("decision.budget_compliance", budget_compliant, hard=True,
               scope="decision", details={
                   "token_budget": token_budget,
                   "total_tokens": total_tokens,
                   "social_actions": observed_social_actions,
                   "max_social_actions": interaction_budget.max_social_actions,
                   "forum_reads": observed_forum_reads,
                   "max_forum_reads": interaction_budget.max_forum_reads,
                   "information_calls": int(lifecycle["information_calls"]),
                   "max_information_calls": MAX_INFO_TURNS,
                   "read_deliveries": len(activity.get("reads") or ()),
               }, **identity),
        _score("decision.belief_valid", belief_valid, hard=True, scope="decision",
               details={"present": belief_present}, **identity),
        _score("decision.belief_present", belief_present, hard=False,
               scope="decision", details={}, **identity),
        _score("decision.prompt_reproducible", prompt_reproducible, hard=False,
               scope="decision", details={"prompts": prompt_identity}, **identity),
    ]


def evaluate_multi_agent(
    messages: Iterable[InteractionMessage],
    *,
    run_id: str,
    expected_agent_ids: Sequence[int],
    schedules: Sequence[Mapping[str, Any]] = (),
    interaction_budget: InteractionBudget = InteractionBudget(),
    model: str = "",
    prompt_versions: Sequence[str] = (),
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

    identity = {
        "run_id": run_id,
        "step_id": f"{run_id}:run:evaluate",
        "model": model,
        "prompt_versions": prompt_versions,
    }
    return [
        _score("multi_agent.sequence_valid", monotonic, hard=True, scope="run",
               details={"messages": len(rows)}, **identity),
        _score("multi_agent.delivery_valid", delivery_valid, hard=True, scope="run",
               details={"known_agents": sorted(expected)}, **identity),
        _score("multi_agent.budget_compliance", budget_valid, hard=True, scope="run",
               details={
                   "max_forum_reads": interaction_budget.max_forum_reads,
                   "max_social_actions": interaction_budget.max_social_actions,
               }, **identity),
        _score("multi_agent.schedule_valid", schedules_valid, hard=True, scope="run",
               details={"ticks": len(schedules)}, **identity),
        _score("multi_agent.participation", participation > 0.0, hard=False,
               scope="run", value=participation,
               details={"participants": sorted(participants & expected),
                        "expected": len(expected)}, **identity),
    ]


@dataclass
class AgentEvaluationSession:
    """Stateful run accumulator; local events remain the source of truth."""

    run_id: str
    interaction_budget: InteractionBudget = InteractionBudget()
    model: str = ""
    schedules: list[dict[str, Any]] = field(default_factory=list)
    beliefs: list[tuple[int, float]] = field(default_factory=list)
    prompt_versions: set[str] = field(default_factory=set)

    def record_schedule(self, *, tick: int, decision_order: Sequence[int]) -> None:
        self.schedules.append({
            "tick": int(tick),
            "decision_order": [int(agent_id) for agent_id in decision_order],
        })

    def score_decision(self, decision: Decision, **kwargs: Any) -> list[EvaluationScore]:
        belief = decision.belief_update
        if belief is not None and _finite_number(belief.get("yes_prob")):
            self.beliefs.append((int(kwargs["agent_id"]), float(belief["yes_prob"])))
        prompt_identity = _public_prompt_identity(decision)
        self.prompt_versions.update(_prompt_versions(prompt_identity))
        score_model = str(kwargs.pop("model", self.model))
        return evaluate_decision(
            decision,
            run_id=self.run_id,
            interaction_budget=self.interaction_budget,
            model=score_model,
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
            model=self.model,
            prompt_versions=sorted(self.prompt_versions),
        )
        target = float(resolved_yes) if resolved_yes in {0, 1} else float(final_yes)
        if self.beliefs:
            brier = sum((belief - target) ** 2 for _, belief in self.beliefs) / len(self.beliefs)
            value = 1.0 - brier
            score_identity = {
                "run_id": self.run_id,
                "step_id": f"{self.run_id}:run:evaluate",
                "model": self.model,
                "prompt_versions": sorted(self.prompt_versions),
            }
            scores.append(_score(
                "run.belief_calibration",
                value >= 0.75,
                hard=False,
                scope="run",
                value=value,
                details={"brier": brier, "target": target, "n": len(self.beliefs)},
                **score_identity,
            ))
        else:
            score_identity = {
                "run_id": self.run_id,
                "step_id": f"{self.run_id}:run:evaluate",
                "model": self.model,
                "prompt_versions": sorted(self.prompt_versions),
            }
            scores.append(_score(
                "run.belief_calibration",
                False,
                hard=False,
                scope="run",
                value=0.0,
                details={"reason": "no_beliefs", "target": target, "n": 0},
                **score_identity,
            ))
        return scores
