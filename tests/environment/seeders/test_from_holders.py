"""Unit tests for environment.seeders.from_holders.seed."""
from __future__ import annotations

import unittest
from unittest import mock

from environment.seeders import from_holders


class _Agent:
    def __init__(self, agent_id: int, src_wallet_addr: str = ""):
        self.agent_id = agent_id
        self.src_wallet_addr = src_wallet_addr
        self.yes_shares = 0.0
        self.no_shares = 0.0


class _Sim:
    def __init__(self, agents):
        self.agents = list(agents)


class FromHoldersSeedTests(unittest.TestCase):
    def test_credits_yes_no_shares_by_outcome_index(self):
        # outcome_index 0 → YES, anything else → NO
        rows = [
            ("0xWALLET_A", 0, 100.0, "Alice"),
            ("0xWALLET_A", 1, 50.0, "Alice"),
            ("0xWALLET_B", 0, 25.0, "Bob"),
        ]
        sim = _Sim([
            _Agent(1, "0xWALLET_A"),
            _Agent(2, "0xWALLET_B"),
        ])
        with mock.patch.object(from_holders.q_holders,
                               "get_top_holders", return_value=rows):
            n = from_holders.seed(sim, "0xCOND")
        self.assertEqual(n, 2)
        self.assertAlmostEqual(sim.agents[0].yes_shares, 100.0)
        self.assertAlmostEqual(sim.agents[0].no_shares, 50.0)
        self.assertAlmostEqual(sim.agents[1].yes_shares, 25.0)
        self.assertAlmostEqual(sim.agents[1].no_shares, 0.0)

    def test_skips_agents_without_src_wallet_addr(self):
        rows = [("0xW", 0, 10.0, "X")]
        sim = _Sim([_Agent(1, ""), _Agent(2, "0xW")])
        with mock.patch.object(from_holders.q_holders,
                               "get_top_holders", return_value=rows):
            n = from_holders.seed(sim, "cond")
        self.assertEqual(n, 1)
        self.assertEqual(sim.agents[0].yes_shares, 0.0)
        self.assertAlmostEqual(sim.agents[1].yes_shares, 10.0)

    def test_skips_unmatched_wallets(self):
        rows = [("0xW_in_data", 0, 1.0, "X")]
        sim = _Sim([_Agent(1, "0xW_NOT_IN_DATA")])
        with mock.patch.object(from_holders.q_holders,
                               "get_top_holders", return_value=rows):
            n = from_holders.seed(sim, "cond")
        self.assertEqual(n, 0)
        self.assertEqual(sim.agents[0].yes_shares, 0.0)


if __name__ == "__main__":
    unittest.main()
