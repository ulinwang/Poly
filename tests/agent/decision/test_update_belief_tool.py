"""v13 (AGT-4) — update_belief tool: schema, parser, env side-effect.

Covers Changes 1+2 from docs/v13/AGT4_REPORT.md:
  - the schema is registered and required fields are correct
  - parse_tool_call dispatches a solo update_belief into an
    UPDATE_BELIEF Decision dict carrying a belief_update payload
  - parse_tool_call clamps yes_prob / confidence to schema range
  - PolyEnv.step persists the belief on AgentRuntime and writes a
    matching UPDATE_BELIEF row to actions_log (both solo and combined-
    with-a-trade paths).
"""
from __future__ import annotations

import unittest

from agent.decision.parser import parse_belief_tool_call, parse_tool_call
from agent.decision.tool_schemas import (
    NAME_TO_ORDER_TYPE, TOOL_SCHEMAS,
)
from agent.decision.types import Decision
from agent.factory import AgentInit
from environment.env import PolyEnv


def _market_meta() -> dict:
    return {
        "condition_id": "0xCID",
        "slug": "test-market",
        "question": "Will it work?",
        "description": "Resolves Yes if it works.",
        "end_date_iso": "2026-12-31T00:00:00",
        "winning_idx": 0,
    }


def _agent(agent_id: int = 0) -> AgentInit:
    return AgentInit(
        wallet_addr=f"0x{agent_id:040x}",
        persona_type="Calibrated", capital_initial=100.0,
        profile_text="test trader",
        private_signal_mu=0.5, private_signal_sigma=0.2,
        risk_aversion=0.5, src_tx_count=10, src_maker_ratio=0.0,
        src_avg_position_usd=10.0, src_asset_diversity=2,
    )


class UpdateBeliefSchemaTest(unittest.TestCase):
    def test_schema_is_registered(self):
        names = [t["function"]["name"] for t in TOOL_SCHEMAS]
        self.assertIn("update_belief", names)
        self.assertEqual(NAME_TO_ORDER_TYPE["update_belief"], "UPDATE_BELIEF")

    def test_required_fields(self):
        schema = next(
            t for t in TOOL_SCHEMAS if t["function"]["name"] == "update_belief"
        )["function"]["parameters"]
        self.assertEqual(
            sorted(schema["required"]),
            ["confidence", "rationale", "yes_prob"],
        )
        # yes_prob bounded to (0.01, 0.99); confidence bounded to (0, 1).
        yp = schema["properties"]["yes_prob"]
        self.assertEqual(yp["minimum"], 0.01)
        self.assertEqual(yp["maximum"], 0.99)


class UpdateBeliefParserTest(unittest.TestCase):
    def test_solo_belief_yields_update_belief_decision(self):
        out = parse_tool_call({
            "id": "tc_1", "name": "update_belief",
            "arguments": {
                "yes_prob": 0.62, "confidence": 0.4,
                "rationale": "evidence shifted slightly bullish",
            },
        })
        self.assertEqual(out["order_type"], "UPDATE_BELIEF")
        self.assertEqual(out["size_usd"], 0.0)
        self.assertAlmostEqual(out["price"], 0.62)
        self.assertEqual(out["reasoning"], "evidence shifted slightly bullish")
        bu = out["belief_update"]
        self.assertAlmostEqual(bu["yes_prob"], 0.62)
        self.assertAlmostEqual(bu["confidence"], 0.4)

    def test_parser_clamps_out_of_range(self):
        out = parse_tool_call({
            "id": "tc_1", "name": "update_belief",
            "arguments": {
                "yes_prob": 1.5, "confidence": -0.3, "rationale": "x",
            },
        })
        self.assertAlmostEqual(out["belief_update"]["yes_prob"], 0.99)
        self.assertAlmostEqual(out["belief_update"]["confidence"], 0.0)

    def test_parse_belief_tool_call_returns_none_for_other_tools(self):
        self.assertIsNone(parse_belief_tool_call({
            "id": "x", "name": "cancel_orders",
            "arguments": {"outcome": "YES", "side": "BUY"},
        }))


class UpdateBeliefEnvIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.env = PolyEnv(
            market_meta=_market_meta(),
            population=[_agent(0)], n_ticks=4, taker_fee_bps=0.0,
        )
        self.env.reset(seed=0)

    def test_solo_belief_decision_sets_runtime_belief(self):
        d = Decision(
            order_type="UPDATE_BELIEF", outcome="YES", side="BUY",
            price=0.62, size_usd=0.0,
            reasoning="bullish on new signal", raw_response="",
            api_latency_ms=0, api_error="",
            belief_update={"yes_prob": 0.62, "confidence": 0.4,
                           "rationale": "bullish on new signal"},
        )
        self.env.step({0: d})
        agent = self.env.state.agents[0]
        self.assertIsNotNone(agent.belief)
        self.assertAlmostEqual(agent.belief["yes_prob"], 0.62)
        self.assertAlmostEqual(agent.belief["confidence"], 0.4)
        self.assertEqual(agent.belief["set_at_tick"], 0)
        # exactly one row, type=UPDATE_BELIEF, no fills
        self.assertEqual(len(self.env.state.actions_log), 1)
        row = self.env.state.actions_log[0]
        # action_type column index 3
        self.assertEqual(row[3], "UPDATE_BELIEF")
        # n_fills = 0
        self.assertEqual(row[11], 0)
        # memory row mirrors the belief
        mem = agent.memory[-1]
        self.assertAlmostEqual(mem["belief_yes_prob"], 0.62)
        self.assertAlmostEqual(mem["belief_confidence"], 0.4)

    def test_combined_trade_and_belief_emit_two_rows(self):
        d = Decision(
            order_type="LIMIT", outcome="YES", side="BUY",
            price=0.42, size_usd=5.0,
            reasoning="entering at the bid", raw_response="",
            api_latency_ms=0, api_error="",
            belief_update={"yes_prob": 0.55, "confidence": 0.6,
                           "rationale": "anchored at 0.55"},
        )
        self.env.step({0: d})
        # two rows: one LIMIT, one UPDATE_BELIEF
        types = [r[3] for r in self.env.state.actions_log]
        self.assertIn("LIMIT", types)
        self.assertIn("UPDATE_BELIEF", types)
        agent = self.env.state.agents[0]
        self.assertIsNotNone(agent.belief)
        self.assertAlmostEqual(agent.belief["yes_prob"], 0.55)


if __name__ == "__main__":
    unittest.main()
