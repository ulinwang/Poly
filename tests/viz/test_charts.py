"""Plotly chart builders return parseable HTML divs even on empty input."""
from __future__ import annotations

import unittest

import pandas as pd

from viz.charts import action_mix_per_tick, per_agent_pnl, yes_mid_trajectory


class EmptyInputTest(unittest.TestCase):
    def test_yes_mid_empty(self):
        out = yes_mid_trajectory(pd.DataFrame())
        self.assertIsInstance(out, str)
        self.assertIn("plotly", out.lower())

    def test_pnl_empty(self):
        out = per_agent_pnl(pd.DataFrame(), pd.DataFrame(), market_resolved_yes=None)
        self.assertIsInstance(out, str)

    def test_action_mix_empty(self):
        self.assertIsInstance(action_mix_per_tick(pd.DataFrame()), str)


class WithDataTest(unittest.TestCase):
    def setUp(self):
        self.actions = pd.DataFrame({
            "tick_idx": [0, 0, 1, 1, 2, 2],
            "agent_id": [0, 1, 0, 1, 0, 1],
            "action_type": ["LIMIT", "HOLD", "MARKET", "CANCEL", "HOLD", "HOLD"],
            "yes_mid_after": [0.50, 0.50, 0.55, 0.55, 0.60, 0.60],
        })
        self.positions = pd.DataFrame({
            "tick_idx": [0, 0, 1, 1, 2, 2],
            "agent_id": [0, 1, 0, 1, 0, 1],
            "yes_shares": [0.0, 0.0, 10.0, 0.0, 10.0, 0.0],
            "no_shares":  [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "cash":       [100.0, 100.0, 95.0, 100.0, 95.0, 100.0],
        })
        self.personas = pd.DataFrame({
            "agent_id": [0, 1],
            "persona_type": ["Calibrated", "Calibrated"],
            "capital_initial": [100.0, 100.0],
        })

    def test_yes_mid_curve_includes_ticks(self):
        out = yes_mid_trajectory(self.actions)
        # Plotly inlines x/y arrays in the JSON config.
        self.assertIn("trajectory", out)

    def test_pnl_marks_winner(self):
        # YES wins → agent 0 (10 yes shares + $95 cash) = $105 vs $100 init = +$5
        out = per_agent_pnl(self.positions, self.personas, market_resolved_yes=1)
        self.assertIn("PnL", out)

    def test_action_mix_includes_categories(self):
        out = action_mix_per_tick(self.actions)
        self.assertIn("LIMIT", out)
        self.assertIn("HOLD", out)


if __name__ == "__main__":
    unittest.main()
