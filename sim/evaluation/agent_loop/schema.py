"""Stable, JSON-safe score records shared by online and offline evals."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping


EVALUATOR_VERSION = "2"


@dataclass(frozen=True)
class EvaluationScore:
    name: str
    value: float
    passed: bool
    hard: bool
    scope: Literal["decision", "run"]
    run_id: str
    evaluator_version: str = EVALUATOR_VERSION
    decision_id: str = ""
    step_id: str = ""
    tick: int | None = None
    agent_id: int | None = None
    model: str = ""
    prompt_versions: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["prompt_versions"] = list(self.prompt_versions)
        record["details"] = dict(self.details)
        return record
