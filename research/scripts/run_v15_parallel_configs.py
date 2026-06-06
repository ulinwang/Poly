"""Run v15 experiment configs in parallel subprocesses.

This is meant for the final rerun where each config already sets its own
agent-level LLM concurrency. The driver adds config-level parallelism while
keeping logs and output directories isolated per config.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "experiments" / "configs" / "v15"
LOG_DIR = ROOT / "output" / "v15" / "parallel_logs"
INDEX_PATH = ROOT / "output" / "v15" / "parallel_index.jsonl"


def iter_configs() -> list[Path]:
    return [
        p for p in sorted(CONFIG_DIR.glob("*.yaml"))
        if not p.name.startswith("smoke_")
    ]


def run_one(path: Path, *, dry_run: bool) -> dict:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    log_path = LOG_DIR / f"{path.stem}.log"
    cmd = [sys.executable, str(ROOT / "scripts" / "run_v15_single_config.py"), str(path)]
    if dry_run:
        cmd.append("--dry-run")
    with log_path.open("w") as log:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, text=True)
    return {
        "config": path.stem,
        "config_path": str(path),
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "seconds": round(time.time() - started, 3),
        "log_path": str(log_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-after", default="")
    parser.add_argument("--start-at", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    configs = iter_configs()
    if args.start_after:
        configs = [p for p in configs if p.stem > args.start_after]
    if args.start_at:
        configs = [p for p in configs if p.stem >= args.start_at]
    if args.limit > 0:
        configs = configs[: args.limit]

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(
        json.dumps(
            {
                "event": "start",
                "workers": args.workers,
                "n_configs": len(configs),
                "configs": [p.stem for p in configs],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    failed = 0
    with futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(run_one, path, dry_run=args.dry_run): path for path in configs}
        for future in futures.as_completed(future_map):
            record = future.result()
            if record["status"] != "ok":
                failed += 1
            line = json.dumps(record, ensure_ascii=False)
            print(line, flush=True)
            with INDEX_PATH.open("a") as fh:
                fh.write(line + "\n")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
