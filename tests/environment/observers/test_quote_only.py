"""quote_only observer must not leak full-book info."""
from __future__ import annotations

import unittest

from agent.decision.types import AgentSnapshot, MarketSnapshot
from environment.observers.quote_only import observe


class _StubBook:
    def __init__(self, bids, asks, mid):
        self.bids = bids
        self.asks = asks
        self._mid = mid

    def best_bid(self):
        return self.bids[0].price if self.bids else None

    def best_ask(self):
        return self.asks[0].price if self.asks else None

    def mid(self):
        return self._mid


class _Order:
    def __init__(self, agent_id, price, remaining=10.0, ts=0):
        self.agent_id = agent_id
        self.price = price
        self.remaining = remaining
        self.ts = ts


class _Sim:
    def __init__(self):
        self.book_yes = _StubBook(
            bids=[_Order(0, 0.45, 20.0), _Order(1, 0.40, 5.0)],
            asks=[_Order(0, 0.52, 10.0), _Order(2, 0.55, 20.0)],
            mid=0.485,
        )
        self.book_no = _StubBook(
            bids=[_Order(0, 0.48, 8.0)], asks=[_Order(0, 0.52, 8.0)], mid=0.50,
        )
        self.yes_mid = 0.485
        self.no_mid = 0.50
        self.yes_mid_history = [0.50, 0.49, 0.485]
        self.n_ticks = 24
        self._ticks_remaining = 20
        self.fills_log = [
            ("sim", 3, 1, 2, 0, 1, "YES", "SELL", 0.52, 4.0, 2.08, None),
            ("sim", 4, 3, 4, 2, 0, "NO", "BUY", 0.48, 3.0, 1.44, None),
        ]

        class _Agent:
            def __init__(self, aid, cash):
                self.agent_id = aid
                self.cash = cash
                self.yes_shares = 0.0
                self.no_shares = 0.0
                self.private_signal_mu = None
                self.private_signal_sigma = None
                self.memory = []
                self.belief = None
        self.agents = [_Agent(0, 100.0), _Agent(1, 50.0)]


class QuoteOnlyObserverTest(unittest.TestCase):
    def test_returns_market_and_agent_snapshots(self):
        sim = _Sim()
        market, agent = observe(sim, agent_id=0)
        self.assertIsInstance(market, MarketSnapshot)
        self.assertIsInstance(agent, AgentSnapshot)
        self.assertEqual(market.yes_best_bid, 0.45)
        self.assertEqual(market.yes_best_ask, 0.52)
        self.assertEqual(agent.cash, 100.0)
        # agent.n_resting_orders should count agent 0's resting orders.
        self.assertEqual(agent.n_resting_orders, 4)  # 1 yes bid + 1 yes ask + 1 no bid + 1 no ask
        self.assertEqual(market.yes_bid_depth[0]["price"], 0.45)
        self.assertEqual(market.yes_bid_depth[0]["size"], 20.0)
        self.assertAlmostEqual(market.yes_order_imbalance, -5 / 55)
        self.assertEqual(len(market.recent_fills), 2)
        self.assertEqual(len(agent.resting_orders), 4)
        self.assertEqual(len(agent.recent_own_fills), 2)

    def test_no_full_book_attributes(self):
        sim = _Sim()
        market, _ = observe(sim, agent_id=0)
        # The MarketSnapshot dataclass must not expose ladder details.
        self.assertFalse(hasattr(market, "all_bids"))
        self.assertFalse(hasattr(market, "all_asks"))

    def test_unknown_agent_raises(self):
        sim = _Sim()
        with self.assertRaises(KeyError):
            observe(sim, agent_id=999)


if __name__ == "__main__":
    unittest.main()
