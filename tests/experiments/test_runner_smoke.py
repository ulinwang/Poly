"""Hermetic runner dry-run smoke test (no ClickHouse, network, or LLM)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from tests._helpers import make_test_population


class RunnerDryRunTest(unittest.TestCase):
    def test_dry_run_writes_full_tree(self):
        from experiments import runner

        meta = {
            "condition_id": "condition-1",
            "slug": "runner-smoke",
            "question": "Will the runner smoke test pass?",
            "description": "Hermetic test market",
            "end_date_iso": "2027-01-01",
            "winning_idx": -1,
        }
        priors = {
            "condition_id": "condition-1",
            "n_ticks": 2,
            "signal_mu": 0.5,
            "tick_size": 0.01,
            "taker_fee_bps": 0.0,
            "bootstrap": {
                "anchor_yes": 0.5,
                "spread": 0.04,
                "depth_per_level": 10.0,
                "depth_levels": 2,
                "source": "test_fixture",
            },
        }

        with tempfile.TemporaryDirectory() as d:
            config = yaml.safe_load(Path(
                "research/experiments/configs/exp001_baseline.yaml"
            ).read_text())
            config["market"]["slug"] = meta["slug"]
            config["output"]["dual_write_clickhouse"] = False
            config_path = Path(d) / "smoke.yaml"
            config_path.write_text(yaml.safe_dump(config))

            with (
                mock.patch.object(runner, "get_market_meta", return_value=meta),
                mock.patch.object(
                    runner,
                    "init_agents",
                    return_value=(make_test_population(3), priors),
                ),
            ):
                exp_id = runner.run_experiment(
                    config_path,
                    output_dir=d,
                    dry_run=True,
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

            # analysis/ — pnl + summary + the table that does not require CH
            self.assertTrue(
                (base / "analysis" / "pnl_by_persona.parquet").exists())
            self.assertTrue((base / "analysis" / "summary.json").exists())
            tables = list((base / "analysis" / "tables").glob("*.md"))
            self.assertGreaterEqual(len(tables), 1)

            # figure/ — price path + PnL are available without live ticks/CH
            figs = list((base / "figure").glob("*.png"))
            self.assertGreaterEqual(len(figs), 2)


if __name__ == "__main__":
    unittest.main()
