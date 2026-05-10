"""full_book observer is currently a stub aliasing quote_only — verify."""
from __future__ import annotations

import unittest

from agent.decision.types import AgentSnapshot, MarketSnapshot
from environment.observers.full_book import observe as full_book_observe
from environment.observers.quote_only import observe as quote_only_observe
from tests.environment.observers.test_quote_only import _Sim


class FullBookObserverTest(unittest.TestCase):
    def test_currently_aliases_quote_only(self):
        sim = _Sim()
        m1, a1 = full_book_observe(sim, 0)
        m2, a2 = quote_only_observe(sim, 0)
        self.assertIsInstance(m1, MarketSnapshot)
        self.assertIsInstance(a1, AgentSnapshot)
        self.assertEqual(m1.yes_best_bid, m2.yes_best_bid)
        self.assertEqual(m1.yes_best_ask, m2.yes_best_ask)
        self.assertEqual(a1.cash, a2.cash)
        self.assertEqual(a1.n_resting_orders, a2.n_resting_orders)


if __name__ == "__main__":
    unittest.main()
