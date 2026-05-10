"""Smoke tests for src/analysis/plots.py.

We don't validate pixel content; we verify that each figure function
saves SOMETHING to disk under both the data-present and data-absent
branches (the latter is the "no v7 sim runs yet" placeholder path
called out in the v7 plan §"Verification").
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.plots import _shared as plots


class _StubCH:
    def __init__(self, route_map: dict):
        self.client = mock.MagicMock()
        self.client.execute.side_effect = lambda sql, params=None: next(
            (rows for substr, rows in route_map.items() if substr in sql),
            [],
        )


class FigureSaveTest(unittest.TestCase):
    def test_fig1_with_data(self):
        ch = _StubCH({
            "FROM polymetl.markets_resolved": [
                (1000.0, 30), (200.0, 7), (50_000.0, 90), (100.0, 2),
            ],
        })
        with tempfile.TemporaryDirectory() as d:
            out = plots.fig1_market_landscape(ch, Path(d))
            self.assertTrue(out.exists())
            self.assertTrue((out.parent / out.stem).with_suffix(".pdf").exists())

    def test_fig1_no_data(self):
        ch = _StubCH({"FROM polymetl.markets_resolved": []})
        with tempfile.TemporaryDirectory() as d:
            out = plots.fig1_market_landscape(ch, Path(d))
            self.assertTrue(out.exists())

    def test_fig2_with_data(self):
        ch = _StubCH({
            "FROM polymetl.wallet_features": [
                (1500.0, 42, 8, 0.55),
                (200.0, 5, 2, 0.45),
                (50000.0, 800, 200, 0.62),
            ],
        })
        with tempfile.TemporaryDirectory() as d:
            out = plots.fig2_wallet_population(ch, "0xCID", Path(d))
            self.assertTrue(out.exists())

    def test_fig2_no_wallets(self):
        ch = _StubCH({"FROM polymetl.wallet_features": []})
        with tempfile.TemporaryDirectory() as d:
            out = plots.fig2_wallet_population(ch, "0xCID", Path(d))
            self.assertTrue(out.exists())

    def test_fig4_serd_roi_no_data(self):
        with tempfile.TemporaryDirectory() as d:
            out = plots.fig4_serd_roi([], Path(d))
            self.assertTrue(out.exists())

    def test_fig4_serd_roi_with_data(self):
        data = [
            ("ApexPredator", 0.15, 12),
            ("UpperMeso", 0.05, 12),
            ("LowerMeso", -0.02, 12),
            ("Prey", -0.10, 12),
        ]
        with tempfile.TemporaryDirectory() as d:
            out = plots.fig4_serd_roi(data, Path(d))
            self.assertTrue(out.exists())

    def test_fig5_vs_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            out = plots.fig5_serd_vs_baseline(0.25, 0.05, Path(d))
            self.assertTrue(out.exists())

    def test_fig6_no_sim_id(self):
        ch = _StubCH({})
        with tempfile.TemporaryDirectory() as d:
            out = plots.fig6_action_mix(ch, sim_id=None, out_dir=Path(d))
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
