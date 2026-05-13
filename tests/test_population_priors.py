"""v8 — derive_priors smoke tests against agent.features.market."""
from __future__ import annotations

import datetime as dt
import json
import unittest

from agent.features import market as dp
from tests.data._stub_ch import StubCH


def _meta_route(_):
    return [(
        "0xCID", "spacex", "Will it work?",
        json.dumps([
            {"token_id": "TYES", "outcome": "Yes"},
            {"token_id": "TNO", "outcome": "No"},
        ]),
        0.001, 0.0,
        dt.datetime(2025, 10, 14), dt.datetime(2025, 9, 10),
        1, dt.datetime(2025, 10, 14), ["Yes", "No"],
        "the desc", 36376.0,
    )]


class DerivePriorsTest(unittest.TestCase):
    def test_full_priors_dict_shape(self):
        first = dt.datetime(2025, 9, 9, 18, 56, 56)
        last = dt.datetime(2025, 10, 14, 0, 0, 0)
        ch = StubCH({
            "FROM polymetl.clob_markets": _meta_route,
            "SELECT min(trade_time)": [(first,)],
            "SELECT max(trade_time)": [(last,)],
            "FROM polymetl.clob_prices_history": [(0, None)],
            "FROM polymetl.clob_orderbook": [(None, None, 0.0)],
            "sum(price * size)": [(0, 0.0, 0.0)],
            "quantile(0.25)(price)": [(20, 0.5, 0.4, 0.6, 100.0)],
        })
        priors = dp.derive_priors("spacex", ch=ch)
        self.assertEqual(priors["schema_version"], "v7-priors-1")
        self.assertEqual(priors["yes_token_id"], "TYES")
        self.assertEqual(priors["bootstrap"]["source"],
                         "dataapi_trades_dispersion")
        self.assertGreaterEqual(priors["n_ticks"], 8)
        self.assertLessEqual(priors["n_ticks"], 48)


class SignalMuSourceSwitchTest(unittest.TestCase):
    """v13 (audit L-6): the signal_mu_source ablation knob must let
    callers swap the private-information anchor at config time."""

    def _ch(self):
        first = dt.datetime(2025, 9, 9, 18, 56, 56)
        last = dt.datetime(2025, 10, 14, 0, 0, 0)
        return StubCH({
            "FROM polymetl.clob_markets": _meta_route,
            "SELECT min(trade_time)": [(first,)],
            "SELECT max(trade_time)": [(last,)],
            # Force the orderbook fallback path → bootstrap anchor=0.5
            "FROM polymetl.clob_prices_history": [(50, 0.42)],
            "FROM polymetl.clob_orderbook": [(None, None, 0.0)],
            "sum(price * size)": [(0, 0.0, 0.0)],
            "quantile(0.25)(price)": [(20, 0.7, 0.6, 0.8, 100.0)],
        })

    def test_default_uses_first_window_vwap(self):
        priors = dp.derive_priors("spacex", ch=self._ch())
        self.assertAlmostEqual(priors["signal_mu"], 0.42)
        self.assertEqual(priors["signal_mu_meta"]["source"],
                         "clob_prices_history")

    def test_bootstrap_anchor_used_when_switched(self):
        priors = dp.derive_priors(
            "spacex", ch=self._ch(),
            signal_mu_source="bootstrap_anchor",
        )
        self.assertAlmostEqual(priors["signal_mu"],
                               priors["bootstrap"]["anchor_yes"])
        self.assertIn("bootstrap_anchor",
                      priors["signal_mu_meta"]["source"])

    def test_unknown_source_raises(self):
        with self.assertRaises(ValueError):
            dp.derive_priors("spacex", ch=self._ch(),
                             signal_mu_source="garbage")


class DeriveSignalMuFallbackTest(unittest.TestCase):
    def test_uses_clob_when_present(self):
        ch = StubCH({
            "FROM polymetl.clob_prices_history": [(50, 0.42)],
        })
        out = dp.derive_signal_mu("0xCID", "TYES", 1_700_000_000, ch=ch)
        self.assertEqual(out["source"], "clob_prices_history")

    def test_falls_back_to_dataapi(self):
        ch = StubCH({
            "FROM polymetl.clob_prices_history": [(0, None)],
            "sum(price * size)": [(10, 4.0, 10.0)],
        })
        out = dp.derive_signal_mu("0xCID", "TYES", 1_700_000_000, ch=ch)
        self.assertEqual(out["source"], "dataapi_trades")
        self.assertAlmostEqual(out["vwap"], 0.4)


if __name__ == "__main__":
    unittest.main()
