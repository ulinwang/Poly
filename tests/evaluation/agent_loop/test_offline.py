from pathlib import Path

from evaluation.agent_loop.cli import main
from evaluation.agent_loop.offline import (
    load_jsonl,
    run_dataset,
    run_langfuse_experiment,
    sync_langfuse_dataset,
)


FIXTURE = Path(__file__).parents[2] / "fixtures" / "agent_loop_eval.jsonl"


def test_checked_in_dataset_has_no_hard_regressions():
    report = run_dataset(load_jsonl(FIXTURE))
    assert report["passed"]
    assert report["hard_failures"] == []


def test_cli_returns_failure_for_hard_regression(tmp_path, monkeypatch):
    source = FIXTURE.read_text(encoding="utf-8")
    row = source.replace('"size_usd":0.0', '"size_usd":5.0', 1)
    path = tmp_path / "regression.jsonl"
    path.write_text(row, encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv", ["poly-eval", str(path), "--fail-on-hard"],
    )
    assert main() == 1


def test_missing_expected_evaluator_is_a_regression():
    case = load_jsonl(FIXTURE)[0]
    case = type(case)(
        case_id=case.case_id,
        input=case.input,
        expected={"pass": ["decision.removed_evaluator"]},
    )
    report = run_dataset([case])
    assert not report["passed"]
    assert report["cases"][0]["expectation_errors"] == [
        "missing:decision.removed_evaluator",
    ]


def test_langfuse_dataset_sync_is_explicit_and_injectable():
    calls = []

    class Client:
        def create_dataset_item(self, **kwargs):
            calls.append(kwargs)

    cases = load_jsonl(FIXTURE)
    count = sync_langfuse_dataset(
        cases, dataset_name="poly-agent-loop-v1", client_factory=Client,
    )
    assert count == 1
    assert calls[0]["dataset_name"] == "poly-agent-loop-v1"


def test_langfuse_experiment_runs_deterministic_task_and_accepts_opt_in_judges():
    calls = []

    class Dataset:
        def run_experiment(self, **kwargs):
            calls.append(kwargs)
            item = type("Item", (), {
                "id": "case",
                "input": load_jsonl(FIXTURE)[0].input,
                "expected_output": {},
            })()
            return kwargs["task"](item=item)

    class Client:
        def get_dataset(self, name):
            assert name == "poly-agent-loop-v1"
            return Dataset()

    judge = lambda **kwargs: kwargs  # noqa: E731 - explicit opt-in test double
    result = run_langfuse_experiment(
        dataset_name="poly-agent-loop-v1",
        experiment_name="prompt-v2",
        evaluators=(judge,),
        client_factory=Client,
    )
    assert result["scores"]
    assert calls[0]["evaluators"] == [judge]
    assert calls[0]["max_concurrency"] == 1
