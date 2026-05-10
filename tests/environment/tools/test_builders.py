from __future__ import annotations

import unittest

from environment.tools import place_order, cancel_order, split_position, merge_position


class PlaceOrderTest(unittest.TestCase):
    def test_limit_builds_decision(self):
        d = place_order.LIMIT(outcome="YES", side="BUY", price=0.55,
                               size_usd=100, reasoning="reason")
        self.assertEqual(d.order_type, "LIMIT")
        self.assertEqual(d.outcome, "YES")
        self.assertEqual(d.price, 0.55)
        self.assertEqual(d.size_usd, 100.0)
        self.assertEqual(d.reasoning, "reason")

    def test_market_zeros_price(self):
        d = place_order.MARKET(outcome="NO", side="SELL", size_usd=50)
        self.assertEqual(d.order_type, "MARKET")
        self.assertEqual(d.price, 0.0)


class CancelOrderTest(unittest.TestCase):
    def test_cancel_zero_size(self):
        d = cancel_order.CANCEL(outcome="YES", side="BUY")
        self.assertEqual(d.order_type, "CANCEL")
        self.assertEqual(d.size_usd, 0.0)


class SplitMergeTest(unittest.TestCase):
    def test_split_carries_size(self):
        d = split_position.SPLIT(size_usd=42)
        self.assertEqual(d.order_type, "SPLIT")
        self.assertEqual(d.size_usd, 42.0)

    def test_merge_carries_pairs(self):
        d = merge_position.MERGE(size_pairs=10)
        self.assertEqual(d.order_type, "MERGE")
        self.assertEqual(d.size_usd, 10.0)


if __name__ == "__main__":
    unittest.main()
