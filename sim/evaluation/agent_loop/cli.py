"""CLI for deterministic Agent Loop regression datasets."""
from __future__ import annotations

import argparse
import json

from evaluation.agent_loop.offline import (
    load_jsonl,
    run_dataset,
    run_langfuse_experiment,
    sync_langfuse_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", help="JSONL dataset containing fixed decisions")
    parser.add_argument("--fail-on-hard", action="store_true")
    parser.add_argument("--langfuse-dataset", default="")
    parser.add_argument("--langfuse-experiment", default="")
    args = parser.parse_args()

    cases = load_jsonl(args.dataset)
    report = run_dataset(cases)
    if args.langfuse_dataset:
        report["langfuse_items_synced"] = sync_langfuse_dataset(
            cases, dataset_name=args.langfuse_dataset,
        )
    if args.langfuse_experiment:
        if not args.langfuse_dataset:
            parser.error("--langfuse-experiment requires --langfuse-dataset")
        result = run_langfuse_experiment(
            dataset_name=args.langfuse_dataset,
            experiment_name=args.langfuse_experiment,
        )
        report["langfuse_experiment"] = str(result)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if args.fail_on_hard and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
