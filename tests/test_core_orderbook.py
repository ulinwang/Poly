from __future__ import annotations

import unittest

from src.core.orderbook import OrderBook


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
        cancels = ob.cancel_all_for_agent(1)
        # v5: returns CancelInfo records so the env layer can release
        # the agent's cash / inventory reservations.
        self.assertEqual(len(cancels), 2)
        sides = sorted(c.side for c in cancels)
        self.assertEqual(sides, ["BUY", "SELL"])
        self.assertTrue(all(c.agent_id == 1 for c in cancels))
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

    def test_misaligned_price_rejected(self):
        ob = OrderBook(tick_size=0.01)
        fills, order = ob.add_limit(1, "BUY", 0.555, 5, ts=0)
        self.assertEqual(fills, [])
        self.assertEqual(order.remaining, 0)
        self.assertIsNone(ob.best_bid())

    def test_aligned_price_accepted(self):
        ob = OrderBook(tick_size=0.01)
        fills, order = ob.add_limit(1, "BUY", 0.55, 5, ts=0)
        self.assertEqual(fills, [])
        self.assertEqual(order.remaining, 5)
        self.assertEqual(ob.best_bid(), 0.55)

    def test_market_sweep_prices_always_allowed(self):
        # tick_size=0.1 means 1.0 is aligned anyway; pick a tick that
        # would make the sweep price misaligned to be sure: tick=0.3.
        # Per spec, prices 0.0 and 1.0 must always be allowed.
        ob = OrderBook(tick_size=0.1)
        # First place a maker SELL @ 0.5 — but 0.5 is aligned w/ 0.1,
        # so use 0.6.
        ob.add_limit(1, "SELL", 0.6, 5, ts=0)
        fills, order = ob.add_market(99, "BUY", size=3, ts=1)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].price, 0.6)
        self.assertEqual(order.remaining, 0)
        # Also confirm sweep-price BUY @ 1.0 is accepted even with an
        # awkward tick that does not divide evenly.
        ob2 = OrderBook(tick_size=0.3)
        # Resting maker at price 0.0 (sweep-extreme) should be allowed:
        # no fills opposite, so just make sure add_market doesn't reject.
        fills2, order2 = ob2.add_market(1, "BUY", size=1, ts=0)
        # Empty book — no fills, but the order should NOT be a 0-size
        # rejection: it's a market sweep with no liquidity to consume.
        self.assertEqual(fills2, [])
        # Sweep at 1.0 with no opposite liquidity rests as a bid @ 1.0,
        # which is the documented behavior of add_market via add_limit.
        # The key check: order.size == requested size (i.e. NOT rejected).
        self.assertEqual(order2.size, 1)

    def test_finer_tick_size(self):
        ob = OrderBook(tick_size=0.001)
        fills, order = ob.add_limit(1, "BUY", 0.555, 5, ts=0)
        self.assertEqual(fills, [])
        self.assertEqual(order.remaining, 5)
        self.assertEqual(ob.best_bid(), 0.555)


class OrderBookMidTest(unittest.TestCase):
    def test_mid_with_tight_spread(self):
        ob = OrderBook(tick_size=0.01)
        ob.add_limit(1, "BUY", 0.40, 5, ts=0)
        ob.add_limit(2, "SELL", 0.45, 5, ts=1)
        self.assertAlmostEqual(ob.mid(), 0.425)

    def test_mid_with_wide_spread_uses_last_trade(self):
        ob = OrderBook(tick_size=0.01)
        # Establish a trade at 0.50 first.
        ob.add_limit(1, "SELL", 0.50, 5, ts=0)
        fills, _ = ob.add_limit(2, "BUY", 0.50, 5, ts=1)
        self.assertEqual(len(fills), 1)
        self.assertEqual(ob.last_trade_price, 0.50)
        # Now create a wide spread: bid @ 0.10, ask @ 0.90.
        ob.add_limit(3, "BUY", 0.10, 5, ts=2)
        ob.add_limit(4, "SELL", 0.90, 5, ts=3)
        # The naive midpoint would be 0.50 by coincidence — to verify
        # we are returning last_trade specifically, mutate the field
        # to a value that could not be the bid/ask midpoint.
        ob.last_trade_price = 0.42
        self.assertEqual(ob.mid(), 0.42)
        # And the spread is indeed wider than 0.10:
        self.assertGreater(ob.best_ask() - ob.best_bid(), 0.10)

    def test_mid_with_wide_spread_no_trades_falls_back_to_single_side(self):
        # Only a bid, no asks, no last trade → mid = bid price.
        ob = OrderBook(tick_size=0.01)
        ob.add_limit(1, "BUY", 0.10, 5, ts=0)
        self.assertIsNone(ob.last_trade_price)
        self.assertEqual(ob.mid(), 0.10)

    def test_last_trade_price_updates_on_each_fill(self):
        ob = OrderBook(tick_size=0.01)
        # Trade #1 at 0.40
        ob.add_limit(1, "SELL", 0.40, 5, ts=0)
        ob.add_limit(2, "BUY", 0.40, 5, ts=1)
        self.assertEqual(ob.last_trade_price, 0.40)
        # Trade #2 at 0.55
        ob.add_limit(3, "SELL", 0.55, 5, ts=2)
        ob.add_limit(4, "BUY", 0.55, 5, ts=3)
        self.assertEqual(ob.last_trade_price, 0.55)


class V5MarketIocTest(unittest.TestCase):
    """C1 fix: MARKET orders are IOC — residual is dropped, never
    rests at the sweep price (1.0 / 0.0). Was the v3/v4 source of
    artifact fills."""

    def test_market_buy_residual_dropped(self):
        ob = OrderBook()
        ob.add_limit(1, "SELL", 0.50, 100, ts=0)   # only 100 shares of supply
        fills, order = ob.add_market(2, "BUY", size=1000, ts=1)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].size, 100)
        self.assertEqual(fills[0].price, 0.50)
        # 900 shares of residual MUST NOT rest as a bid at 1.0.
        self.assertEqual(len(ob.bids), 0)
        self.assertEqual(len(ob.asks), 0)

    def test_market_sell_residual_dropped(self):
        ob = OrderBook()
        ob.add_limit(1, "BUY", 0.50, 50, ts=0)
        fills, order = ob.add_market(2, "SELL", size=200, ts=1)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].size, 50)
        # No 0-priced ask residual.
        self.assertEqual(len(ob.asks), 0)
        self.assertEqual(len(ob.bids), 0)

    def test_subsequent_limit_does_not_pick_up_artifact(self):
        # The exact Run #5b Tick 10 scenario: agent 3 MARKET BUY YES
        # leaves residual at 1.0; agent 4 LIMIT SELL @ 0.30 used to
        # match against that residual at price 1.0. Post-fix it must
        # not.
        ob = OrderBook()
        ob.add_limit(1, "SELL", 0.50, 100, ts=0)
        ob.add_market(2, "BUY", size=1000, ts=1)   # residual would have been at 1.0
        # Agent 3 places LIMIT SELL @ 0.30. With v3/v4 it matched at 1.0.
        fills, order = ob.add_limit(3, "SELL", 0.30, 5, ts=2)
        self.assertEqual(fills, [])
        self.assertEqual(order.remaining, 5)   # the SELL rests as ask
        self.assertEqual(ob.best_ask(), 0.30)


class V5SelfMatchPreventionTest(unittest.TestCase):
    """C3: same agent's crossing pair triggers cancel-resting; same
    agent's NON-crossing pair (legitimate two-sided quotes) does not."""

    def test_self_match_cancels_resting(self):
        ob = OrderBook()
        # Agent 1 buys at 0.40
        _, buy = ob.add_limit(1, "BUY", 0.40, 100, ts=0)
        # Agent 1 then SELLs at 0.30 — would cross their own bid.
        fills, sell = ob.add_limit(1, "SELL", 0.30, 100, ts=1)
        # No fill: self-match prevention cancelled the resting BUY.
        self.assertEqual(fills, [])
        self.assertEqual(len(ob.bids), 0)
        # The new SELL rests on the ask side.
        self.assertEqual(ob.best_ask(), 0.30)
        # CancelInfo recorded for env to free the maker's reservation.
        self.assertEqual(len(ob.self_match_cancellations), 1)
        ci = ob.self_match_cancellations[0]
        self.assertEqual(ci.agent_id, 1)
        self.assertEqual(ci.side, "BUY")
        self.assertEqual(ci.price, 0.40)
        self.assertEqual(ci.remaining_size, 100)

    def test_two_sided_quote_not_cancelled(self):
        # MM agent 1 quotes BUY @ 0.40 + SELL @ 0.50. Spread > 0, no
        # cross. Both should sit on the book.
        ob = OrderBook()
        ob.add_limit(1, "BUY", 0.40, 50, ts=0)
        ob.add_limit(1, "SELL", 0.50, 50, ts=1)
        self.assertEqual(ob.best_bid(), 0.40)
        self.assertEqual(ob.best_ask(), 0.50)
        self.assertEqual(ob.self_match_cancellations, [])

    def test_self_match_during_market_order(self):
        # Agent 1 has a resting BUY @ 0.40, then issues MARKET SELL.
        # Their own bid should be cancelled (not self-traded).
        ob = OrderBook()
        # Agent 2 is a real counterparty at 0.45 (better bid).
        ob.add_limit(2, "BUY", 0.45, 50, ts=0)
        ob.add_limit(1, "BUY", 0.40, 30, ts=1)
        fills, _ = ob.add_market(1, "SELL", size=80, ts=2)
        # Should fill 50 against agent 2's 0.45 bid; then encounter
        # own 0.40 bid which gets cancelled (no self-fill); then
        # nothing left — drop residual 30.
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].maker_agent_id, 2)
        self.assertEqual(fills[0].size, 50)
        # Agent 1's own 0.40 bid was cancelled (not filled).
        self.assertEqual(len(ob.self_match_cancellations), 1)
        self.assertEqual(ob.self_match_cancellations[0].agent_id, 1)


if __name__ == "__main__":
    unittest.main()
