"""Offline JSONL dataset replay with optional Langfuse dataset sync."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from agent.decision import Decision
from agent.multi_agent.protocol import InteractionBudget
from evaluation.agent_loop.evaluators import evaluate_decision
from evaluation.agent_loop.schema import EvaluationScore


@dataclass(frozen=True)
class DatasetCase:
    case_id: str
    input: Mapping[str, Any]
    expected: Mapping[str, Any]


def load_jsonl(path: str | Path) -> list[DatasetCase]:
    cases: list[DatasetCase] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            cases.append(DatasetCase(
                case_id=str(row.get("case_id") or f"line-{line_number}"),
                input=dict(row["input"]),
                expected=dict(row.get("expected") or {}),
            ))
    return cases


def evaluate_case(case: DatasetCase) -> list[EvaluationScore]:
    data = dict(case.input)
    decision = Decision(**dict(data.pop("decision")))
    budget = InteractionBudget(**dict(data.pop("interaction_budget", {})))
    return evaluate_decision(decision, interaction_budget=budget, **data)


def run_dataset(cases: Iterable[DatasetCase]) -> dict[str, Any]:
    results = []
    hard_failures = []
    for case in cases:
        scores = evaluate_case(case)
        expected_pass = set(case.expected.get("pass", ()))
        expected_fail = set(case.expected.get("fail", ()))
        expectation_errors = [
            score.name for score in scores
            if (score.name in expected_pass and not score.passed)
            or (score.name in expected_fail and score.passed)
        ]
        failures = [score.name for score in scores if score.hard and not score.passed]
        if failures or expectation_errors:
            hard_failures.append(case.case_id)
        results.append({
            "case_id": case.case_id,
            "scores": [score.to_record() for score in scores],
            "expectation_errors": expectation_errors,
        })
    return {
        "dataset_version": "1",
        "cases": results,
        "n_cases": len(results),
        "hard_failures": hard_failures,
        "passed": not hard_failures,
    }


def sync_langfuse_dataset(
    cases: Iterable[DatasetCase],
    *,
    dataset_name: str,
    client_factory: Callable[[], Any] | None = None,
) -> int:
    """Explicit opt-in extension point; never called by normal evaluation."""
    if client_factory is None:
        from langfuse import Langfuse
        client_factory = Langfuse
    client = client_factory()
    count = 0
    for case in cases:
        client.create_dataset_item(
            dataset_name=dataset_name,
            id=case.case_id,
            input=dict(case.input),
            expected_output=dict(case.expected),
            metadata={"poly_dataset_version": "1"},
        )
        count += 1
    return count


def run_langfuse_experiment(
    *,
    dataset_name: str,
    experiment_name: str,
    evaluators: Iterable[Callable[..., Any]] = (),
    client_factory: Callable[[], Any] | None = None,
) -> Any:
    """Run deterministic Poly evals over a synced Langfuse dataset.

    Extra Langfuse-compatible evaluators may be supplied explicitly (including
    an LLM-as-a-judge). They are never enabled by the local CLI or CI defaults.
    """
    if client_factory is None:
        from langfuse import Langfuse
        client_factory = Langfuse
    client = client_factory()
    dataset = client.get_dataset(dataset_name)

    def task(*, item: Any, **_: Any) -> dict[str, Any]:
        case = DatasetCase(
            case_id=str(getattr(item, "id", "langfuse-item")),
            input=dict(item.input),
            expected=dict(getattr(item, "expected_output", None) or {}),
        )
        return {
            "scores": [score.to_record() for score in evaluate_case(case)],
        }

    return dataset.run_experiment(
        name=experiment_name,
        description="Poly deterministic Agent Loop regression",
        task=task,
        evaluators=list(evaluators),
        max_concurrency=1,
        metadata={"poly_dataset_version": "1"},
    )
