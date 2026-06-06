"""v13 — Multi-run driver for named experiment suites.

CLI
---
Run all configs in a suite (filename glob ``b1_*.yaml``, ``c1_*.yaml`` etc.):

    python scripts/run_experiment_suite.py --suite b1 \
        --output-dir output/v13/b1 \
        [--dry-run] [--max-parallel 1] [--config-dir experiments/configs]

Behavior
--------
1. Glob ``experiments/configs/<suite>_*.yaml`` (default config dir).
2. For each YAML, call ``experiments.runner.run_experiment`` with
   ``--dry-run`` propagated. Failures are caught and logged; the
   suite continues.
3. If ``suite == 'b1'`` (or a directory containing
   ``b1_markets.yaml``), expand the template ``b1_template.yaml``
   per market into a temp YAML, one experiment per market.
4. Write ``<output_dir>/index.json`` summarizing
   ``{suite, n_runs, runs: [{config_path, exp_id, status, error?}]}``.

Concurrency
-----------
Default sequential. ``--max-parallel N`` runs up to N experiments at
once with a thread pool (the runner itself uses thread parallelism
for per-tick LLM calls; the outer pool is for separate market
simulations). Be polite — DeepSeek rate limits.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Optional

import yaml


log = logging.getLogger(__name__)


# ---------------------------------------------------------------
# B1 template expansion
# ---------------------------------------------------------------


def _expand_b1_template(
    template_path: Path, markets_yaml: Path, tmp_dir: Path,
) -> list[Path]:
    """Write one per-market YAML under ``tmp_dir`` and return paths.

    The template's ``market.slug`` placeholder ``"{slug}"`` is
    replaced with each row's slug; experiment ``name`` is suffixed
    with the slug for uniqueness."""
    if not template_path.exists():
        raise FileNotFoundError(template_path)
    tmpl = yaml.safe_load(template_path.read_text()) or {}
    markets_doc = yaml.safe_load(markets_yaml.read_text()) or {}
    markets = markets_doc.get("markets") or []
    if not markets:
        raise ValueError(f"no markets in {markets_yaml}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for m in markets:
        cfg = json.loads(json.dumps(tmpl))  # deep copy
        slug = str(m["slug"])
        cfg.setdefault("market", {})["slug"] = slug
        # name uniqueness: slugify a bit
        safe_slug = re.sub(r"[^a-z0-9_-]", "_", slug)[:48]
        cfg["name"] = f"{tmpl.get('name', 'b1')}_{safe_slug}"
        p = tmp_dir / f"b1_{safe_slug}.yaml"
        p.write_text(yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False))
        paths.append(p)
    return paths


# ---------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------


def discover_configs(
    suite: str, config_dir: Path,
    tmp_dir: Optional[Path] = None,
) -> list[Path]:
    """Glob ``{suite}_*.yaml`` under ``config_dir``; if suite=='b1'
    and ``b1_template.yaml`` + ``b1_markets.yaml`` exist, expand
    those instead."""
    if suite == "b1":
        tmpl = config_dir / "b1_template.yaml"
        mks = config_dir / "b1_markets.yaml"
        if tmpl.exists() and mks.exists():
            td = tmp_dir or Path(tempfile.mkdtemp(prefix="b1_suite_"))
            return _expand_b1_template(tmpl, mks, td)
    matches = sorted(config_dir.glob(f"{suite}_*.yaml"))
    # Exclude meta files like b1_markets.yaml and template files
    return [p for p in matches if not p.name.endswith("_markets.yaml")
            and not p.name.endswith("_template.yaml")]


# ---------------------------------------------------------------
# Execution
# ---------------------------------------------------------------


def _run_one(
    cfg_path: Path, output_dir: Path, dry_run: bool,
    runner_fn=None,
) -> dict:
    """Run a single experiment; return a status dict.

    ``runner_fn`` defaults to ``experiments.runner.run_experiment``;
    tests inject their own."""
    if runner_fn is None:
        from experiments.runner import run_experiment as runner_fn  # type: ignore  # noqa
    record: dict = {
        "config_path": str(cfg_path),
        "name": cfg_path.stem,
        "exp_id": None,
        "status": "pending",
    }
    try:
        exp_id = runner_fn(
            str(cfg_path), output_dir=str(output_dir), dry_run=dry_run,
        )
        record["exp_id"] = exp_id
        record["status"] = "ok"
    except SystemExit as exc:
        record["status"] = "failed"
        record["error"] = f"SystemExit: {exc}"
        log.warning("run %s failed: %s", cfg_path, exc)
    except Exception as exc:  # noqa: BLE001
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        log.exception("run %s raised", cfg_path)
    return record


def run_suite(
    suite: str, *,
    config_dir: Path = Path("experiments/configs"),
    output_dir: Path = Path("output/v13"),
    dry_run: bool = False,
    max_parallel: int = 1,
    runner_fn=None,
) -> dict:
    """Run every config in ``suite``. Returns a dict written to
    ``<output_dir>/index.json``."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = output_dir / "_expanded_configs" if suite == "b1" else None
    configs = discover_configs(suite, config_dir, tmp_dir=tmp_dir)
    log.info("suite=%s: discovered %d configs", suite, len(configs))
    if not configs:
        index = {"suite": suite, "n_runs": 0, "runs": []}
        (output_dir / "index.json").write_text(json.dumps(index, indent=2))
        return index

    records: list[dict] = []
    if max_parallel <= 1:
        for p in configs:
            records.append(_run_one(p, output_dir, dry_run, runner_fn))
    else:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_parallel,
            thread_name_prefix=f"suite-{suite}",
        ) as pool:
            futures = {pool.submit(_run_one, p, output_dir, dry_run, runner_fn): p
                       for p in configs}
            for fut in concurrent.futures.as_completed(futures):
                records.append(fut.result())
    index = {
        "suite": suite,
        "n_runs": len(records),
        "n_ok": sum(1 for r in records if r["status"] == "ok"),
        "n_failed": sum(1 for r in records if r["status"] == "failed"),
        "dry_run": dry_run,
        "runs": records,
    }
    (output_dir / "index.json").write_text(json.dumps(index, indent=2,
                                                      default=str))
    log.info("suite=%s done: %d/%d ok",
             suite, index["n_ok"], index["n_runs"])
    return index


# ---------------------------------------------------------------
# CLI
# ---------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", required=True,
                        help="suite prefix (for example b1, b4, c1, c2)")
    parser.add_argument("--output-dir", type=Path,
                        default=Path("output/v13"))
    parser.add_argument("--config-dir", type=Path,
                        default=Path("experiments/configs"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-parallel", type=int, default=1)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    idx = run_suite(
        suite=args.suite,
        config_dir=args.config_dir,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        max_parallel=args.max_parallel,
    )
    print(json.dumps(idx, indent=2, default=str))
    return 0 if idx.get("n_failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
