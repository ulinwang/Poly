from __future__ import annotations

import unittest

from src.sim.orderbook import OrderBook


class OrderBookBasicsTest(unittest.TestCase):
    def test_empty_book_mid_returns_fallback(self):
        ob = OrderBook()
        self.assertEqual(ob.mid(), 0.5)
        self.assertIsNone(ob.best_bid())
        self.assertIsNone(ob.best_ask())

    def test_resting_limit_order(self):
        ob = OrderBook()
        fills, order = ob.add_limit(agent_id=1, side="BUY", price=0.40, size=10, ts=0)
        self.assertEqual(fills, [])
        self.assertEqual(order.remaining, 10)
        self.assertEqual(ob.best_bid(), 0.40)

    def test_no_cross_no_match(self):
        ob = OrderBook()
        ob.add_limit(1, "BUY", 0.40, 10, 0)
        fills, order = ob.add_limit(2, "SELL", 0.50, 5, 0)
        self.assertEqual(fills, [])
        self.assertEqual(order.remaining, 5)


class OrderBookMatchingTest(unittest.TestCase):
    def test_buy_crosses_sell_at_makers_price(self):
        ob = OrderBook()
        # Maker SELL @ 0.50
        ob.add_limit(1, "SELL", 0.50, 10, ts=0)
        # Taker BUY @ 0.55 (crosses)
        fills, order = ob.add_limit(2, "BUY", 0.55, 4, ts=1)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].price, 0.50)  # maker price wins
        self.assertEqual(fills[0].size, 4)
        self.assertEqual(fills[0].maker_agent_id, 1)
        self.assertEqual(fills[0].taker_agent_id, 2)
        self.assertEqual(order.remaining, 0)
        # Maker has 6 left
        self.assertEqual(ob.best_ask(), 0.50)
        self.assertEqual(ob.depth_at("SELL")[0][1], 6)

    def test_partial_fill_then_resting(self):
        ob = OrderBook()
        ob.add_limit(1, "SELL", 0.50, 3, ts=0)
        # BUY 5 @ 0.50: should consume 3, then rest 2 as bid @ 0.50
        fills, order = ob.add_limit(2, "BUY", 0.50, 5, ts=1)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].size, 3)
        self.assertAlmostEqual(order.remaining, 2)
        self.assertEqual(ob.best_bid(), 0.50)
        self.assertIsNone(ob.best_ask())

    def test_price_time_priority(self):
        ob = OrderBook()
        ob.add_limit(1, "SELL", 0.50, 5, ts=0)
        ob.add_limit(2, "SELL", 0.50, 5, ts=1)   # ties at 0.50, ts=1 second
        ob.add_limit(3, "SELL", 0.45, 5, ts=2)   # better price first
        # First filler should be agent 3 (best price), then 1 (older), then 2
        fills, _ = ob.add_limit(99, "BUY", 0.60, 12, ts=3)
        makers = [f.maker_agent_id for f in fills]
        self.assertEqual(makers, [3, 1, 2])

    def test_market_order_sweeps_book(self):
        ob = OrderBook()
        ob.add_limit(1, "SELL", 0.40, 5, ts=0)
        ob.add_limit(2, "SELL", 0.50, 5, ts=1)
        fills, order = ob.add_market(99, "BUY", size=8, ts=2)
        self.assertEqual([f.price for f in fills], [0.40, 0.50])
        self.assertEqual([f.size for f in fills], [5, 3])
        self.assertEqual(order.remaining, 0)


class OrderBookCancelTest(unittest.TestCase):
    def test_cancel_removes_from_book(self):
        ob = OrderBook()
        _, o1 = ob.add_limit(1, "BUY", 0.40, 5, ts=0)
        ob.add_limit(2, "BUY", 0.30, 5, ts=1)
        ok = ob.cancel(o1.order_id)
        self.assertTrue(ok)
        self.assertEqual(ob.best_bid(), 0.30)

    def test_cancel_unknown_returns_false(self):
        ob = OrderBook()
        self.assertFalse(ob.cancel(9999))

    def test_cancel_all_for_agent(self):
        ob = OrderBook()
        ob.add_limit(1, "BUY", 0.40, 5, ts=0)
        ob.add_limit(1, "SELL", 0.60, 5, ts=0)
        ob.add_limit(2, "BUY", 0.35, 5, ts=0)
        n = ob.cancel_all_for_agent(1)
        self.assertEqual(n, 2)
        self.assertEqual(ob.best_bid(), 0.35)
        self.assertIsNone(ob.best_ask())


class OrderBookEdgeTest(unittest.TestCase):
    def test_zero_size_returns_no_fills(self):
        ob = OrderBook()
        ob.add_limit(1, "SELL", 0.5, 5, ts=0)
        fills, order = ob.add_limit(2, "BUY", 0.6, 0, ts=1)
        self.assertEqual(fills, [])
        self.assertEqual(order.remaining, 0.0)

    def test_out_of_range_price_creates_no_fill(self):
        ob = OrderBook()
        fills, _ = ob.add_limit(1, "BUY", 1.5, 5, ts=0)
        self.assertEqual(fills, [])

    def test_depth_at_aggregates_by_price(self):
        ob = OrderBook()
        ob.add_limit(1, "BUY", 0.40, 3, ts=0)
        ob.add_limit(2, "BUY", 0.40, 5, ts=1)   # same price
        ob.add_limit(3, "BUY", 0.30, 4, ts=2)
        d = ob.depth_at("BUY")
        self.assertEqual(d[0], (0.40, 8))
        self.assertEqual(d[1], (0.30, 4))


if __name__ == "__main__":
    unittest.main()
