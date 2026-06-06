"""`python -m experiments {run|list|show}`."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from experiments.runner import run_experiment


def cmd_run(args: argparse.Namespace) -> None:
    exp_id = run_experiment(
        args.config, output_dir=args.output_dir, dry_run=args.dry_run,
    )
    print(f"exp_id: {exp_id}")


def cmd_list(args: argparse.Namespace) -> None:
    out = Path(args.output_dir)
    if not out.exists():
        print(f"(no experiments under {out})")
        return
    rows: list[tuple[str, str, str]] = []
    for d in sorted(out.iterdir()):
        meta_p = d / "meta.json"
        if not meta_p.exists():
            continue
        try:
            meta = json.loads(meta_p.read_text())
        except Exception:           # noqa: BLE001
            continue
        rows.append((
            d.name,
            meta.get("config", {}).get("name", "-"),
            str(meta.get("n_agents", "-")),
        ))
    if not rows:
        print(f"(no meta.json under {out})")
        return
    print(f"{'exp_id':<54}  {'name':<14}  {'n_agents':>8}")
    print("-" * 80)
    for r in rows:
        print(f"{r[0]:<54}  {r[1]:<14}  {r[2]:>8}")


def cmd_show(args: argparse.Namespace) -> None:
    p = Path(args.output_dir) / args.exp_id / "meta.json"
    if not p.exists():
        raise SystemExit(f"no meta at {p}")
    print(p.read_text())


def main() -> None:
    parser = argparse.ArgumentParser(prog="experiments")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run an experiment from a YAML config")
    p_run.add_argument("config")
    p_run.add_argument("--output-dir", default="output")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list", help="list experiments under output/")
    p_list.add_argument("--output-dir", default="output")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="dump meta.json for one experiment")
    p_show.add_argument("exp_id")
    p_show.add_argument("--output-dir", default="output")
    p_show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args.func(args)


if __name__ == "__main__":
    main()
