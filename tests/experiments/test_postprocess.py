"""Unit tests for experiments.postprocess.

Strategy: build a minimal `_FakeSim`, fake a `_FakeAgent`/`_FakePersona`,
write priors_<slug>.json into a tmp data_dir, and run the public entry
points without ClickHouse — tab1/2/3, plot subsets that need CH, and
SERD analysis are gracefully skipped when ch=None.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from experiments import postprocess as pp


# ----- Fakes --------------------------------------------------------------
class _FakePersona:
    def __init__(self, ptype): self.persona_type = ptype


class _FakeAgent:
    def __init__(self, agent_id, persona_type="P"):
        self.agent_id = agent_id
        self.persona = _FakePersona(persona_type)


class _FakeSim:
    def __init__(self, sim_id="sim_t", agents=None, fills_log=None):
        self.sim_id = sim_id
        self.agents = agents or [_FakeAgent(0, "P"), _FakeAgent(1, "Q")]
        self.fills_log = fills_log if fills_log is not None else []
        self.n_ticks = 24


class _FakeSerdReport:
    def __init__(self):
        self.n_agents = 5
        self.delta_roi_serd = 0.42
        self.delta_roi_baseline = 0.10
        self.monotonic = True
        self.roi_per_role = {"L": {"mean_roi": 0.1, "n": 1}}
        self.role_of = {0: "L", 1: "F"}


# ----- Tests --------------------------------------------------------------
class WriteRoleAssignmentsTests(unittest.TestCase):
    def test_writes_parquet_with_expected_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            n = pp._write_role_assignments(
                "sim_x",
                role_of={0: "L", 1: "F"},
                roi_role={"L": {"mean_roi": 0.5}, "F": {"mean_roi": -0.1}},
                out_dir=out_dir,
            )
            self.assertEqual(n, 2)
            df = pd.read_parquet(out_dir / "analysis" / "role_assignments.parquet")
            self.assertEqual(set(df.columns),
                              {"sim_id", "agent_id", "role", "role_mean_roi"})
            self.assertEqual(len(df), 2)


class WritePnlByPersonaTests(unittest.TestCase):
    def test_aggregates_and_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            pnl = {0: 10.0, 1: 20.0, 2: -5.0}
            persona_of = {0: "P", 1: "P", 2: "Q"}
            n = pp._write_pnl_by_persona("sim_x", pnl, persona_of, out_dir)
            self.assertEqual(n, 2)  # two persona buckets
            df = pd.read_parquet(out_dir / "analysis" / "pnl_by_persona.parquet")
            self.assertIn("persona_type", df.columns)
            self.assertIn("mean", df.columns)


class WriteSummaryJsonTests(unittest.TestCase):
    def test_minimal_writes_summary_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            pp.write_summary_json(
                out_dir, sim_id="sim_x", n_agents=2, n_ticks=10,
                pnl={0: 5.0, 1: -1.0}, priors_summary={"k": "v"},
            )
            data = json.loads((out_dir / "analysis" / "summary.json").read_text())
            self.assertEqual(data["sim_id"], "sim_x")
            self.assertEqual(data["n_agents"], 2)
            self.assertEqual(data["n_ticks"], 10)
            self.assertAlmostEqual(data["pnl_mean"], 2.0)
            self.assertEqual(data["priors"], {"k": "v"})
            self.assertNotIn("serd", data)

    def test_with_serd_report_includes_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            pp.write_summary_json(
                out_dir, sim_id="sim_x", n_agents=5, n_ticks=24,
                pnl={0: 1.0}, priors_summary={},
                serd_report=_FakeSerdReport(),
            )
            data = json.loads((out_dir / "analysis" / "summary.json").read_text())
            self.assertIn("serd", data)
            self.assertEqual(data["serd"]["n_agents"], 5)
            self.assertAlmostEqual(data["serd"]["delta_roi_serd"], 0.42)
            self.assertTrue(data["serd"]["monotonic"])

    def test_empty_pnl_yields_zero_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            pp.write_summary_json(
                out_dir, sim_id="x", n_agents=0, n_ticks=0,
                pnl={}, priors_summary={},
            )
            d = json.loads((out_dir / "analysis" / "summary.json").read_text())
            self.assertEqual(d["pnl_mean"], 0.0)
            self.assertEqual(d["pnl_min"], 0.0)
            self.assertEqual(d["pnl_max"], 0.0)


class WriteTablesTests(unittest.TestCase):
    def test_no_ch_only_renders_tab4(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            (data_dir / "priors_my-slug.json").write_text(json.dumps({
                "condition_id": "0xCID",
                "market_open_iso": "2026-01-01",
                "tick_size": 0.01,
                "taker_fee_bps": 0.0001,
                "n_ticks": 24,
                "signal_mu": 0.5,
                "signal_mu_meta": {"source": "stub", "n_obs": 0},
                "bootstrap": {"anchor_yes": 0.5, "spread": 0.02,
                              "depth_per_level": 100, "depth_levels": 3,
                              "source": "stub"},
                "winning_idx": -1,
            }))
            out_dir = Path(tmp) / "out"
            paths = pp._write_tables(out_dir, "my-slug", None, data_dir, ch=None)
            self.assertIn("tab4", paths)
            md = (out_dir / "analysis" / "tables" / "tab4_priors_summary.md").read_text()
            self.assertIn("Prior", md)
            # tab1/2/3 must not exist
            self.assertFalse((out_dir / "analysis" / "tables"
                              / "tab1_wallet_population.md").exists())


class WriteFiguresTests(unittest.TestCase):
    def test_returns_empty_when_all_plots_raise(self):
        # No CH passed and tries to render fig4/fig5 from the role_summary
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()

            with mock.patch(
                "experiments.plots._shared.fig4_serd_roi",
                side_effect=RuntimeError("nope"),
            ), mock.patch(
                "experiments.plots._shared.fig5_serd_vs_baseline",
                side_effect=RuntimeError("nope2"),
            ):
                # Should not raise — failures swallowed.
                final = pp._write_figures(
                    out_dir, "my-slug", "sim_x", data_dir, ch=None,
                )
            self.assertEqual(final, [])


class RunPostprocessTests(unittest.TestCase):
    def test_no_ch_skips_serd_and_writes_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "exp"
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            (data_dir / "priors_my-slug.json").write_text(json.dumps({
                "condition_id": "0xCID",
                "market_open_iso": "2026-01-01",
                "tick_size": 0.01, "taker_fee_bps": 0.0,
                "n_ticks": 24, "signal_mu": 0.5,
                "signal_mu_meta": {"source": "x", "n_obs": 0},
                "bootstrap": {"anchor_yes": 0.5, "spread": 0.02,
                              "depth_per_level": 100, "depth_levels": 3,
                              "source": "x"},
                "winning_idx": -1, "yes_token_id": "T1",
            }))
            sim = _FakeSim()
            pnl = {0: 10.0, 1: -1.0}
            result = pp.run_postprocess(
                out_dir=out_dir, slug="my-slug", sim=sim, pnl=pnl,
                priors_summary={"slug": "my-slug"},
                data_dir=data_dir, ch=None,
            )
            self.assertIsNone(result["serd_report"])
            self.assertEqual(result["role_summary"], [])
            self.assertTrue((out_dir / "analysis" / "summary.json").exists())
            self.assertTrue((out_dir / "analysis"
                              / "pnl_by_persona.parquet").exists())


if __name__ == "__main__":
    unittest.main()
