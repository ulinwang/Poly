"""tape observer is currently a stub aliasing quote_only — verify."""
from __future__ import annotations

import unittest

from agent.decision.types import AgentSnapshot, MarketSnapshot
from environment.observers.tape import observe as tape_observe
from environment.observers.quote_only import observe as quote_only_observe
from tests.environment.observers.test_quote_only import _Sim


class TapeObserverTest(unittest.TestCase):
    def test_currently_aliases_quote_only(self):
        sim = _Sim()
        m1, a1 = tape_observe(sim, 0)
        m2, a2 = quote_only_observe(sim, 0)
        self.assertIsInstance(m1, MarketSnapshot)
        self.assertIsInstance(a1, AgentSnapshot)
        self.assertEqual(m1.yes_mid, m2.yes_mid)
        self.assertEqual(m1.yes_mid_history, m2.yes_mid_history)


if __name__ == "__main__":
    unittest.main()
