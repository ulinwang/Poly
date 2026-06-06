"""Run v15 experiment configs using each config's declared output directory.

Unlike scripts/run_experiment_suite.py, this driver preserves per-config
output.output_dir so c1_robotaxi, c3_ethereum, and other suites stay grouped.

Examples:
    uv run python scripts/run_v15_experiment_configs.py --smoke
    uv run python scripts/run_v15_experiment_configs.py --dry-run
    uv run python scripts/run_v15_experiment_configs.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from experiments.runner import load_config, run_experiment


ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "experiments" / "configs" / "v15"


def iter_configs(*, smoke: bool = False) -> list[Path]:
    if smoke:
        return [CONFIG_DIR / "smoke_2agent_t3.yaml"]
    return [
        p for p in sorted(CONFIG_DIR.glob("*.yaml"))
        if not p.name.startswith("smoke_")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-after", default="")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    configs = iter_configs(smoke=args.smoke)
    if args.start_after:
        configs = [p for p in configs if p.stem > args.start_after]
    if args.limit > 0:
        configs = configs[:args.limit]

    records: list[dict] = []
    for idx, path in enumerate(configs, start=1):
        cfg = load_config(path)
        print(f"[{idx}/{len(configs)}] {path.name} -> {cfg.output.output_dir}", flush=True)
        record = {
            "config_path": str(path),
            "name": cfg.name,
            "output_dir": cfg.output.output_dir,
            "exp_id": None,
            "status": "pending",
        }
        try:
            exp_id = run_experiment(
                path,
                output_dir=cfg.output.output_dir,
                dry_run=args.dry_run,
            )
            record["exp_id"] = exp_id
            record["status"] = "ok"
        except SystemExit as exc:
            record["status"] = "failed"
            record["error"] = f"SystemExit: {exc}"
            records.append(record)
            break
        except Exception as exc:  # noqa: BLE001
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
            records.append(record)
            break
        records.append(record)

    index_dir = ROOT / "output" / "v15"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_name = "smoke_index.json" if args.smoke else "index.json"
    payload = {
        "dry_run": args.dry_run,
        "smoke": args.smoke,
        "n_runs": len(records),
        "n_ok": sum(1 for r in records if r["status"] == "ok"),
        "n_failed": sum(1 for r in records if r["status"] == "failed"),
        "runs": records,
    }
    (index_dir / index_name).write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["n_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
