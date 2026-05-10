"""v7 — wallet_features.compute_features unit tests.

Pure pytest-friendly unittest; no DB required. We feed
`compute_features` the same row shape `dataapi_trades` returns
(condition_id, outcome_index, price, size, trade_time) and assert
the aggregated fingerprint is correct.
"""
from __future__ import annotations

import datetime as dt
import unittest

from agent.features.wallet import compute_features


def _t(cid, oidx, p, s, t=None):
    return (cid, oidx, p, s, t or dt.datetime(2025, 1, 1))


class ComputeFeaturesTest(unittest.TestCase):
    def test_empty_trades_returns_zeros(self):
        out = compute_features([], {})
        self.assertEqual(out["tx_count"], 0)
        self.assertEqual(out["capital_usd"], 0.0)
        self.assertEqual(out["past_accuracy"], 0.0)
        self.assertEqual(out["n_resolved_prior"], 0)

    def test_basic_aggregation(self):
        trades = [
            _t("A", 0, 0.5, 100),
            _t("A", 0, 0.6, 200),
            _t("B", 1, 0.3, 50),
        ]
        out = compute_features(trades, {})
        self.assertEqual(out["tx_count"], 3)
        self.assertEqual(out["asset_diversity"], 2)
        self.assertAlmostEqual(out["capital_usd"], 0.5*100 + 0.6*200 + 0.3*50)

    def test_past_accuracy_capital_weighted(self):
        # Wallet bet 100 on A:Yes (won) and 200 on B:Yes (lost).
        # A resolved Yes (winning_idx=0), B resolved No (winning_idx=1).
        trades = [
            _t("A", 0, 1.0, 100),   # cap=100 on winning side
            _t("B", 0, 1.0, 200),   # cap=200 on losing side
        ]
        resolved = {"A": 0, "B": 1}
        out = compute_features(trades, resolved)
        self.assertEqual(out["n_resolved_prior"], 2)
        # 100 winning / (100+200) total = 1/3
        self.assertAlmostEqual(out["past_accuracy"], 100.0 / 300.0)

    def test_unresolved_market_excluded_from_accuracy(self):
        trades = [
            _t("A", 0, 1.0, 100),   # winning
            _t("C", 0, 1.0, 50),    # unresolved (-1)
        ]
        resolved = {"A": 0, "C": -1}
        out = compute_features(trades, resolved)
        # n_resolved_prior counts only resolved markets
        self.assertEqual(out["n_resolved_prior"], 1)
        # past_accuracy is 100% (only the resolved one is included)
        self.assertEqual(out["past_accuracy"], 1.0)

    def test_placeholders_remain_zero(self):
        # maker_ratio + avg_holding_h are honest placeholders per
        # the audit; v7 keeps them as 0.0 for schema parity.
        trades = [_t("A", 0, 0.5, 100)]
        out = compute_features(trades, {"A": 0})
        self.assertEqual(out["maker_ratio"], 0.0)
        self.assertEqual(out["avg_holding_h"], 0.0)


if __name__ == "__main__":
    unittest.main()
