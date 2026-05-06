from __future__ import annotations

import unittest

from src.sim import wallet_calibration as wc


class FeatureExtractionTest(unittest.TestCase):
    def test_empty_returns_zeros(self):
        out = wc.compute_features([], [])
        self.assertEqual(out["tx_count"], 0)
        self.assertEqual(out["capital_usd"], 0.0)
        self.assertEqual(out["asset_diversity"], 0)
        self.assertEqual(out["past_accuracy"], 0.0)

    def test_basic_aggregates(self):
        trades = [
            {"price": 0.50, "size": 100, "conditionId": "0xA"},
            {"price": 0.40, "size": 50, "conditionId": "0xA"},
            {"price": 0.10, "size": 200, "conditionId": "0xB"},   # maker (0.01<p<0.99)
            {"price": 0.99, "size": 10, "conditionId": "0xC"},    # boundary, taker
        ]
        positions = [
            {"realizedPnl": 5.0, "avgPrice": 0.5, "totalBought": 100},  # win, cap=50
            {"realizedPnl": -3.0, "avgPrice": 0.4, "totalBought": 50},   # loss, cap=20
        ]
        out = wc.compute_features(trades, positions)
        self.assertEqual(out["tx_count"], 4)
        # capital_usd = sum(price*size) = 50 + 20 + 20 + 9.9 = 99.9
        self.assertAlmostEqual(out["capital_usd"], 99.9, places=2)
        # avg_position_usd = mean of those = 24.975
        self.assertAlmostEqual(out["avg_position_usd"], 24.975, places=2)
        # 3 of 4 trades are within (0.01, 0.99) — exact boundary 0.99 excluded
        self.assertAlmostEqual(out["maker_ratio"], 0.75, places=2)
        # 3 distinct conditionIds
        self.assertEqual(out["asset_diversity"], 3)
        # past_accuracy: win capital 50 / total capital 70 = 0.714
        self.assertAlmostEqual(out["past_accuracy"], 50.0 / 70.0, places=3)
        self.assertEqual(out["n_resolved_prior"], 2)

    def test_maker_ratio_bounds(self):
        # all extreme prices → all takers → ratio 0
        out = wc.compute_features(
            [{"price": 0.999, "size": 1, "conditionId": "x"}], [],
        )
        self.assertEqual(out["maker_ratio"], 0.0)

    def test_past_accuracy_no_capital(self):
        # closed positions but no capital → defaults to 0
        positions = [{"realizedPnl": 5.0, "avgPrice": 0, "totalBought": 0}]
        out = wc.compute_features([], positions)
        self.assertEqual(out["past_accuracy"], 0.0)


class StratifiedSampleTest(unittest.TestCase):
    def test_returns_all_when_smaller(self):
        out = wc.stratified_sample(["a", "b", "c"], 5)
        self.assertEqual(set(out), {"a", "b", "c"})

    def test_caps_at_n(self):
        out = wc.stratified_sample(["a", "b", "c", "d", "e"], 3, seed=42)
        self.assertEqual(len(out), 3)

    def test_n_zero_returns_empty(self):
        self.assertEqual(wc.stratified_sample(["a", "b"], 0), [])

    def test_deterministic_with_seed(self):
        a = wc.stratified_sample(["a", "b", "c", "d", "e"], 3, seed=7)
        b = wc.stratified_sample(["a", "b", "c", "d", "e"], 3, seed=7)
        self.assertEqual(a, b)


class ToFloatTest(unittest.TestCase):
    def test_handles_strings(self):
        self.assertEqual(wc._to_float("3.14"), 3.14)

    def test_handles_none(self):
        self.assertEqual(wc._to_float(None), 0.0)

    def test_default(self):
        self.assertEqual(wc._to_float("oops", default=-1.0), -1.0)


if __name__ == "__main__":
    unittest.main()
