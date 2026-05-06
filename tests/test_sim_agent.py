from __future__ import annotations

import unittest

from src.sim.agent import parse_decision, round_to_tick


class ParseSplitMergeTest(unittest.TestCase):
    def test_split_parses(self):
        out = parse_decision(
            '{"order_type":"SPLIT","outcome":"YES","side":"BUY",'
            '"price":0,"size_usd":100,"reasoning":"seed"}'
        )
        self.assertEqual(out["order_type"], "SPLIT")
        self.assertEqual(out["size_usd"], 100.0)

    def test_merge_parses_with_missing_outcome(self):
        out = parse_decision(
            '{"order_type":"MERGE","size_usd":50,"reasoning":"flatten"}'
        )
        self.assertEqual(out["order_type"], "MERGE")
        self.assertEqual(out["size_usd"], 50.0)


class TickRoundingTest(unittest.TestCase):
    def test_limit_price_rounded(self):
        out = parse_decision(
            '{"order_type":"LIMIT","outcome":"YES","side":"BUY",'
            '"price":0.555,"size_usd":10,"reasoning":"x"}'
        )
        self.assertAlmostEqual(out["price"], 0.56, places=2)

    def test_limit_price_already_aligned(self):
        out = parse_decision(
            '{"order_type":"LIMIT","outcome":"YES","side":"BUY",'
            '"price":0.50,"size_usd":10,"reasoning":"x"}'
        )
        self.assertAlmostEqual(out["price"], 0.50, places=2)

    def test_round_to_tick_helper(self):
        self.assertAlmostEqual(round_to_tick(0.123), 0.12, places=2)


if __name__ == "__main__":
    unittest.main()
