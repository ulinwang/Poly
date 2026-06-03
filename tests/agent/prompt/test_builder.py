"""Jinja2 template rendering for system + user prompts."""
from __future__ import annotations

import unittest

from agent.personas.persona import Persona
from agent.decision.types import AgentSnapshot, MarketSnapshot
from agent.prompt.builder import (
    build_clob_system_prompt, build_simple_system_prompt, build_user_prompt,
)


class ClobSystemPromptTest(unittest.TestCase):
    def test_calibrated_omits_risk_aversion(self):
        p = Persona("Calibrated", 0.5, 1000.0, "thoughtful trader")
        out = build_clob_system_prompt(p, "Q?", "Rules.", "2026-12-31")
        self.assertNotIn("Risk aversion", out)
        self.assertIn("thoughtful trader", out)
        self.assertIn("Q?", out)

    def test_handcoded_includes_risk_aversion(self):
        p = Persona("HandCoded", 0.7, 1000.0, "p")
        out = build_clob_system_prompt(p, "Q?", "Rules.", "2026-12-31")
        self.assertIn("Risk aversion: 0.7", out)

    def test_long_description_truncated(self):
        p = Persona("Calibrated", 0.5, 1000.0, "p")
        out = build_clob_system_prompt(p, "Q?", "x" * 5000, "2026-01-01")
        self.assertIn("[truncated]", out)

    def test_tick_size_propagates(self):
        p = Persona("Calibrated", 0.5, 1000.0, "p")
        out = build_clob_system_prompt(p, "Q?", "R", "2026-01-01", tick_size=0.001)
        self.assertIn("0.001", out)

    def test_chinese_system_prompt(self):
        p = Persona("Calibrated", 0.5, 1000.0, "谨慎交易者")
        out = build_clob_system_prompt(
            p, "Q?", "Rules.", "2026-12-31", prompt_language="zh",
        )
        self.assertIn("你是 Polymarket 预测市场交易者", out)
        self.assertIn("谨慎交易者", out)
        self.assertIn("第一阶段先更新", out)


class SimpleSystemPromptTest(unittest.TestCase):
    def test_renders_text_template(self):
        p = Persona("Calibrated", 0.5, 1000.0, "thoughtful trader")
        out = build_simple_system_prompt(p, "Q?", "Rules.", "2026-12-31")
        self.assertIn("thoughtful trader", out)
        self.assertIn("Q?", out)


class UserPromptTest(unittest.TestCase):
    def _market(self):
        return MarketSnapshot(
            yes_best_bid=0.4, yes_best_ask=0.5, yes_mid=0.45,
            no_best_bid=0.5, no_best_ask=0.6, no_mid=0.55,
            yes_mid_history=[0.50, 0.48, 0.45],
            ticks_remaining=10, total_ticks=48,
            yes_bid_depth=[{"price": 0.40, "size": 20.0}],
            yes_ask_depth=[{"price": 0.50, "size": 10.0}],
            no_bid_depth=[{"price": 0.50, "size": 12.0}],
            no_ask_depth=[{"price": 0.60, "size": 18.0}],
            yes_order_imbalance=0.33,
            no_order_imbalance=-0.20,
            recent_fills=[{
                "tick": 7, "outcome": "YES", "maker_side": "SELL",
                "price": 0.50, "size": 2.0, "notional": 1.0,
            }],
        )

    def _agent(self, with_signal=False):
        return AgentSnapshot(
            agent_id=1, cash=100.0, yes_shares=0.0, no_shares=0.0,
            n_resting_orders=0,
            private_signal_mu=0.6 if with_signal else None,
            private_signal_sigma=0.2 if with_signal else None,
            resting_orders=[{
                "outcome": "YES", "side": "BUY", "price": 0.40,
                "remaining": 2.0, "age_ticks": 3,
            }],
            recent_own_fills=[{
                "tick": 7, "role": "taker", "outcome": "YES",
                "maker_side": "SELL", "price": 0.50,
                "size": 2.0, "notional": 1.0,
            }],
        )

    def test_renders_books_and_portfolio(self):
        out = build_user_prompt(self._market(), self._agent())
        self.assertIn("YES book", out)
        self.assertIn("NO book", out)
        self.assertIn("YES bid depth", out)
        self.assertIn("Order imbalance", out)
        self.assertIn("Recent public fills", out)
        self.assertIn("Your resting orders", out)
        self.assertIn("Your recent fills", out)
        self.assertIn("$100.00", out)
        self.assertIn("21%", out)  # 10/48 ≈ 21%

    def test_includes_signal_block_when_set(self):
        out = build_user_prompt(self._market(), self._agent(with_signal=True))
        self.assertIn("private prior", out)
        self.assertIn("0.60", out)

    def test_omits_signal_block_when_unset(self):
        out = build_user_prompt(self._market(), self._agent())
        self.assertNotIn("private prior", out)

    def test_chinese_user_prompt(self):
        out = build_user_prompt(
            self._market(), self._agent(with_signal=True),
            prompt_language="zh",
        )
        self.assertIn("当前订单簿", out)
        self.assertIn("你的组合", out)
        self.assertIn("私人先验", out)
        self.assertIn("近期公开成交", out)


if __name__ == "__main__":
    unittest.main()
