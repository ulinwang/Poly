"""v13 (AGT-4) — user_state.j2 must surface the agent's explicit
belief state (Change 3).

Two cases covered:
  - When `belief_snapshot` is set: the template renders P(YES),
    confidence, rationale, and the "ticks_ago" age.
  - When `belief_snapshot` is None: the template renders the
    "have not yet stated a belief" nudge.
"""
from __future__ import annotations

import unittest

from agent.decision.types import AgentSnapshot, MarketSnapshot
from agent.prompt.builder import build_user_prompt


def _market(total_ticks: int = 24, ticks_remaining: int = 19) -> MarketSnapshot:
    return MarketSnapshot(
        yes_best_bid=0.45, yes_best_ask=0.55, yes_mid=0.50,
        no_best_bid=0.45, no_best_ask=0.55, no_mid=0.50,
        yes_mid_history=[0.49, 0.50, 0.50],
        ticks_remaining=ticks_remaining, total_ticks=total_ticks,
    )


def _agent_with_belief(belief: dict | None) -> AgentSnapshot:
    return AgentSnapshot(
        agent_id=0, cash=100.0, yes_shares=0.0, no_shares=0.0,
        n_resting_orders=0, recent_decisions=None,
        belief_snapshot=belief,
    )


class UserStateBeliefTest(unittest.TestCase):
    def test_belief_present_renders_posterior_block(self):
        belief = {"yes_prob": 0.62, "confidence": 0.4,
                  "rationale": "tilt bullish on the new statement",
                  "set_at_tick": 2}
        text = build_user_prompt(
            _market(total_ticks=24, ticks_remaining=19),  # current_tick = 5
            _agent_with_belief(belief),
        )
        self.assertIn("Your current stated belief", text)
        self.assertIn("0.62", text)
        self.assertIn("0.4", text)            # confidence value
        self.assertIn("tilt bullish", text)
        # ticks_ago = 5 - 2 = 3
        self.assertIn("3 ticks ago", text)
        # No "have not yet stated" nudge in this branch
        self.assertNotIn("have not yet stated a belief", text)

    def test_no_belief_renders_anchor_nudge(self):
        text = build_user_prompt(
            _market(), _agent_with_belief(None),
        )
        self.assertIn("have not yet stated a belief", text)
        self.assertIn("update_belief", text)
        # No "stated belief" header in this branch
        self.assertNotIn("Your current stated belief", text)


if __name__ == "__main__":
    unittest.main()
