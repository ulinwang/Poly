"""Unit tests for agent.memory.episodic.EpisodicMemory."""
from __future__ import annotations

import unittest

from agent.memory.episodic import EpisodicMemory


class EpisodicMemoryTests(unittest.TestCase):
    def test_default_field_values(self):
        m = EpisodicMemory(agent_id=42)
        self.assertEqual(m.agent_id, 42)
        self.assertEqual(m.recent_decisions, [])
        self.assertEqual(m.private_belief_mu, 0.5)
        self.assertEqual(m.private_belief_sigma, 0.2)
        self.assertEqual(m.last_action_tick, -1)

    def test_remember_appends_with_tick(self):
        m = EpisodicMemory(agent_id=1)
        m.remember(5, {"action": "BUY", "size": 10})
        self.assertEqual(len(m.recent_decisions), 1)
        self.assertEqual(m.recent_decisions[0]["tick"], 5)
        self.assertEqual(m.recent_decisions[0]["action"], "BUY")
        self.assertEqual(m.recent_decisions[0]["size"], 10)
        self.assertEqual(m.last_action_tick, 5)

    def test_remember_caps_at_32_keeping_most_recent(self):
        m = EpisodicMemory(agent_id=1)
        for tick in range(40):
            m.remember(tick, {"action": "HOLD"})
        self.assertEqual(len(m.recent_decisions), 32)
        # most recent 32 = ticks 8..39
        self.assertEqual(m.recent_decisions[0]["tick"], 8)
        self.assertEqual(m.recent_decisions[-1]["tick"], 39)
        self.assertEqual(m.last_action_tick, 39)

    def test_distinct_instances_have_independent_lists(self):
        a = EpisodicMemory(agent_id=1)
        b = EpisodicMemory(agent_id=2)
        a.remember(0, {"action": "BUY"})
        self.assertEqual(b.recent_decisions, [])


if __name__ == "__main__":
    unittest.main()
