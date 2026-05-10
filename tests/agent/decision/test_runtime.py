"""decide() integration with a stubbed tool-mode LLM."""
from __future__ import annotations

import unittest

from agent.decision.runtime import decide
from agent.decision.types import AgentSnapshot, MarketSnapshot
from agent.personas.persona import Persona


def _persona() -> Persona:
    return Persona(
        persona_type="Calibrated", risk_aversion=0.5,
        capital_initial=100.0, profile_text="thoughtful trader",
    )


def _market() -> MarketSnapshot:
    return MarketSnapshot(
        yes_best_bid=0.4, yes_best_ask=0.5, yes_mid=0.45,
        no_best_bid=0.5, no_best_ask=0.6, no_mid=0.55,
        yes_mid_history=[0.50, 0.48, 0.45],
        ticks_remaining=10, total_ticks=48,
    )


def _agent_state() -> AgentSnapshot:
    return AgentSnapshot(
        agent_id=1, cash=100.0, yes_shares=0.0, no_shares=0.0,
        n_resting_orders=0,
    )


class DecideToolCallingTest(unittest.TestCase):
    def test_tool_call_translates_to_decision(self):
        def fake_llm(**kwargs):
            return {
                "tool_call": {
                    "id": "tc_1",
                    "name": "place_limit_order",
                    "arguments": {
                        "outcome": "YES", "side": "BUY",
                        "price": 0.42, "size_usd": 50,
                        "reasoning": "below fair value",
                    },
                },
                "text": "",
                "raw": "{...}",
                "prompt_tokens": 10, "completion_tokens": 5,
            }

        d = decide(
            persona=_persona(), question="Q?", description="R", end_date="2026",
            market=_market(), agent=_agent_state(),
            api_key="x", base_url="x", model="x",
            call_fn=fake_llm, max_attempts=1,
        )
        self.assertEqual(d.order_type, "LIMIT")
        self.assertEqual(d.outcome, "YES")
        self.assertEqual(d.size_usd, 50.0)
        self.assertEqual(d.reasoning, "below fair value")
        self.assertEqual(d.api_error, "")

    def test_no_tool_call_is_hold(self):
        def fake_llm(**kwargs):
            return {"tool_call": None, "text": "I'll wait.",
                    "raw": "{}", "prompt_tokens": 0, "completion_tokens": 0}

        d = decide(
            persona=_persona(), question="Q?", description="R", end_date="2026",
            market=_market(), agent=_agent_state(),
            api_key="x", base_url="x", model="x",
            call_fn=fake_llm, max_attempts=1,
        )
        self.assertEqual(d.order_type, "HOLD")
        # decline-text becomes the reasoning
        self.assertIn("wait", d.reasoning)

    def test_llm_failure_returns_hold_with_error(self):
        def boom(**kwargs):
            raise ValueError("rate limited")

        d = decide(
            persona=_persona(), question="Q?", description="R", end_date="2026",
            market=_market(), agent=_agent_state(),
            api_key="x", base_url="x", model="x",
            call_fn=boom, max_attempts=1,
        )
        self.assertEqual(d.order_type, "HOLD")
        self.assertIn("rate limited", d.api_error)


if __name__ == "__main__":
    unittest.main()
