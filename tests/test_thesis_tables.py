"""Smoke tests for src/thesis/tables.py: markdown + LaTeX formatting."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.analysis import tables


class _StubCH:
    def __init__(self, route_map: dict):
        self.client = mock.MagicMock()
        self.client.execute.side_effect = lambda sql, params=None: next(
            (rows for substr, rows in route_map.items() if substr in sql), [],
        )


class FormattingTest(unittest.TestCase):
    def test_md_table_headers_and_rows(self):
        out = tables._md_table(["A", "B"], [["1", "2"], ["3", "4"]])
        self.assertIn("| A | B |", out)
        self.assertIn("| 1 | 2 |", out)
        self.assertIn("| --- | --- |", out)

    def test_latex_table_envelope(self):
        out = tables._latex_table(
            ["A", "B"], [["1", "2"]], caption="Foo", label="tab:foo",
        )
        self.assertIn(r"\begin{table}", out)
        self.assertIn(r"\caption{Foo}", out)
        self.assertIn(r"\label{tab:foo}", out)
        self.assertIn(r"\end{table}", out)


class WalletPopulationTest(unittest.TestCase):
    def test_renders_summary_stats(self):
        rows = [
            (100.0, 5, 2, 0.5, 1),
            (1000.0, 50, 20, 0.7, 10),
            (10000.0, 500, 200, 0.6, 100),
        ]
        ch = _StubCH({"FROM polymetl.wallet_features": rows})
        md, tex = tables.render_wallet_population(ch, "0xCID")
        self.assertIn("min", md)
        self.assertIn("median", md)
        self.assertIn("mean", md)
        self.assertIn("n = 3", md)
        self.assertIn(r"\caption", tex)

    def test_empty_wallets(self):
        ch = _StubCH({"FROM polymetl.wallet_features": []})
        md, _ = tables.render_wallet_population(ch, "0xCID")
        self.assertIn("(no rows)", md)


class PriorsSummaryTest(unittest.TestCase):
    def test_renders_priors_from_json(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "priors_foo.json").write_text(json.dumps({
                "market_open_iso": "2025-09-09T18:56:56",
                "tick_size": 0.001,
                "taker_fee_bps": 0.0,
                "n_ticks": 24,
                "signal_mu": 0.679,
                "signal_mu_meta": {"source": "dataapi_trades", "n_obs": 2},
                "bootstrap": {"anchor_yes": 0.667, "spread": 0.03,
                              "depth_per_level": 10, "depth_levels": 3,
                              "source": "dataapi_trades_dispersion"},
                "winning_idx": 1,
            }))
            md, tex = tables.render_priors_summary("foo", Path(d))
            self.assertIn("0.679", md)
            self.assertIn("dataapi_trades", md)
            self.assertIn(r"\label{tab:priors_summary}", tex)

    def test_missing_json(self):
        md, _ = tables.render_priors_summary("nope", Path("/tmp"))
        self.assertIn("not found", md)


if __name__ == "__main__":
    unittest.main()
