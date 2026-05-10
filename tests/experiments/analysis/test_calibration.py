"""Unit tests for experiments.analysis.calibration — pure-math functions."""
from __future__ import annotations

import datetime as dt
import math
import unittest

from experiments.analysis.calibration import (
    pearson, real_price_path, compare_paths, direction_correct,
)


class PearsonTests(unittest.TestCase):
    def test_perfect_positive_correlation_is_one(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [2.0, 4.0, 6.0, 8.0]
        self.assertAlmostEqual(pearson(xs, ys), 1.0, places=10)

    def test_perfect_negative_correlation_is_minus_one(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [4.0, 3.0, 2.0, 1.0]
        self.assertAlmostEqual(pearson(xs, ys), -1.0, places=10)

    def test_constant_series_returns_zero(self):
        self.assertEqual(pearson([0.5] * 5, [1.0, 2.0, 3.0, 4.0, 5.0]), 0.0)

    def test_unequal_lengths_returns_zero(self):
        self.assertEqual(pearson([1.0, 2.0], [1.0, 2.0, 3.0]), 0.0)

    def test_too_few_samples_returns_zero(self):
        self.assertEqual(pearson([1.0], [1.0]), 0.0)


class RealPricePathTests(unittest.TestCase):
    def setUp(self):
        self.start = dt.datetime(2026, 1, 1, 0, 0, 0)
        self.end = dt.datetime(2026, 1, 1, 4, 0, 0)  # 4 hour span
        # tuple shape: (.., .., trade_time, side, price, size, ..)
        self.trades = [
            (None, None, dt.datetime(2026, 1, 1, 0, 30), "BUY", 0.6, 10.0),
            (None, None, dt.datetime(2026, 1, 1, 1, 30), "BUY", 0.7, 5.0),
            (None, None, dt.datetime(2026, 1, 1, 3, 30), "SELL", 0.4, 20.0),
        ]

    def test_buckets_distribute_trades_by_time(self):
        path = real_price_path(self.trades, n_buckets=4, start=self.start, end=self.end)
        self.assertEqual(len(path), 4)
        # bucket 0: only first trade @ 0.6 → 0.6
        self.assertAlmostEqual(path[0], 0.6)
        # bucket 1: only second trade @ 0.7 → 0.7
        self.assertAlmostEqual(path[1], 0.7)
        # bucket 2: no trades → carry last (0.7)
        self.assertAlmostEqual(path[2], 0.7)
        # bucket 3: third trade @ 0.4
        self.assertAlmostEqual(path[3], 0.4)

    def test_volume_weighted_average(self):
        # two trades same bucket: prices 0.6@10 and 0.8@30 → vwap = (6+24)/40 = 0.75
        trades = [
            (None, None, dt.datetime(2026, 1, 1, 0, 30), "B", 0.6, 10.0),
            (None, None, dt.datetime(2026, 1, 1, 0, 45), "B", 0.8, 30.0),
        ]
        path = real_price_path(trades, n_buckets=2, start=self.start, end=self.end)
        self.assertAlmostEqual(path[0], 0.75, places=6)

    def test_empty_trades_returns_default_halves(self):
        path = real_price_path([], n_buckets=5, start=self.start, end=self.end)
        self.assertEqual(path, [0.5] * 5)

    def test_zero_buckets_returns_empty(self):
        # n_buckets <= 0 -> [0.5] * 0 = []
        self.assertEqual(real_price_path(self.trades, 0, self.start, self.end), [])

    def test_end_before_start_returns_default(self):
        path = real_price_path(self.trades, 3, self.end, self.start)
        self.assertEqual(path, [0.5] * 3)


class ComparePathsTests(unittest.TestCase):
    def test_lengths_mismatch_raises(self):
        with self.assertRaises(ValueError):
            compare_paths([0.5, 0.5], [0.5, 0.5, 0.5])

    def test_returns_pearson_mae_finaldiff(self):
        sim = [0.5, 0.6, 0.7, 0.8]
        real = [0.4, 0.5, 0.6, 0.7]
        out = compare_paths(sim, real)
        self.assertIn("pearson_r", out)
        self.assertIn("mae", out)
        self.assertIn("final_diff", out)
        self.assertAlmostEqual(out["mae"], 0.1, places=10)
        self.assertAlmostEqual(out["final_diff"], 0.1, places=10)
        self.assertAlmostEqual(out["pearson_r"], 1.0, places=10)


class DirectionCorrectTests(unittest.TestCase):
    def test_yes_resolved_above_half_is_correct(self):
        self.assertTrue(direction_correct(0.7, 1))

    def test_yes_resolved_below_half_is_wrong(self):
        self.assertFalse(direction_correct(0.3, 1))

    def test_no_resolved_below_half_is_correct(self):
        self.assertTrue(direction_correct(0.3, 0))

    def test_no_resolved_above_half_is_wrong(self):
        self.assertFalse(direction_correct(0.6, 0))


if __name__ == "__main__":
    unittest.main()
