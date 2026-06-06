"""Run one v15 experiment config without rewriting the suite index."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from experiments.runner import load_config, run_experiment


ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "experiments" / "configs" / "v15"


def resolve_config(name_or_path: str) -> Path:
    path = Path(name_or_path)
    if path.exists():
        return path
    candidate = CONFIG_DIR / f"{name_or_path.removesuffix('.yaml')}.yaml"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"v15 config not found: {name_or_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="Config stem, .yaml name, or path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    path = resolve_config(args.config)
    cfg = load_config(path)
    record = {
        "config_path": str(path),
        "name": cfg.name,
        "output_dir": cfg.output.output_dir,
        "exp_id": None,
        "status": "pending",
    }
    try:
        record["exp_id"] = run_experiment(path, output_dir=cfg.output.output_dir, dry_run=args.dry_run)
        record["status"] = "ok"
    except Exception as exc:  # noqa: BLE001
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
        return 1

    print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
