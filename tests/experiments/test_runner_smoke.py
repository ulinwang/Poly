"""Runner happy path with a real SpaceX dry-run.

Skips when wallet_features rows or cached personas are missing
(non-thesis dev environments)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


SLUG = "will-the-chopsticks-catch-spacex-starship-flight-test-11-superheavy-booster"


def _spacex_priors_exists() -> bool:
    return Path("data") / f"priors_{SLUG}.json" in Path("data").glob("priors_*.json")


def _personas_cached() -> bool:
    p = Path("data/wallet_personas.json")
    if not p.exists():
        return False
    try:
        cache = json.loads(p.read_text())
    except Exception:    # noqa: BLE001
        return False
    # cache is keyed by condition_id; spacex condition starts with 0x2f6384.
    return any(k.startswith("0x2f6384adfb9c0045") for k in cache)


@unittest.skipUnless(_personas_cached(), "spacex personas not cached locally")
class RunnerDryRunTest(unittest.TestCase):
    def test_dry_run_writes_full_tree(self):
        from experiments.runner import run_experiment

        with tempfile.TemporaryDirectory() as d:
            exp_id = run_experiment(
                "experiments/configs/exp001_baseline.yaml",
                output_dir=d, dry_run=True,
            )
            base = Path(d) / exp_id

            self.assertTrue((base / "meta.json").exists())
            meta = json.loads((base / "meta.json").read_text())
            self.assertEqual(meta["config"]["name"], "baseline")
            self.assertGreater(meta["n_agents"], 0)

            # raw/ — 4 parquet files always written
            for f in ("agent_actions", "agent_fills",
                      "agent_positions", "agent_personas"):
                self.assertTrue(
                    (base / "raw" / f"{f}.parquet").exists(),
                    f"missing raw/{f}.parquet",
                )

            # analysis/ — pnl + summary + at least 2 tables
            self.assertTrue(
                (base / "analysis" / "pnl_by_persona.parquet").exists())
            self.assertTrue((base / "analysis" / "summary.json").exists())
            tables = list((base / "analysis" / "tables").glob("*.md"))
            self.assertGreaterEqual(len(tables), 2)

            # figure/ — at least 4 of 6 in dry-run
            figs = list((base / "figure").glob("*.png"))
            self.assertGreaterEqual(len(figs), 4)


if __name__ == "__main__":
    unittest.main()
