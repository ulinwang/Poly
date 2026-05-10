"""parse_tool_call: OpenAI tool_call → engine decision dict."""
from __future__ import annotations

import unittest

from agent.decision.parser import parse_tool_call


def _tc(name: str, **arguments) -> dict:
    return {"id": "tc_1", "name": name, "arguments": dict(arguments)}


class ParseToolCallTest(unittest.TestCase):
    def test_none_tool_call_is_hold(self):
        out = parse_tool_call(None)
        self.assertEqual(out["order_type"], "HOLD")
        self.assertEqual(out["size_usd"], 0.0)

    def test_empty_dict_is_hold(self):
        out = parse_tool_call({})
        self.assertEqual(out["order_type"], "HOLD")

    def test_unknown_tool_is_hold_with_diagnostic(self):
        out = parse_tool_call(_tc("frobnicate", x=1))
        self.assertEqual(out["order_type"], "HOLD")
        self.assertIn("unknown_tool", out["reasoning"])

    def test_place_limit_round_trip(self):
        out = parse_tool_call(_tc(
            "place_limit_order",
            outcome="YES", side="BUY", price=0.555, size_usd=100,
            reasoning="thoughtful entry",
        ))
        self.assertEqual(out["order_type"], "LIMIT")
        self.assertEqual(out["outcome"], "YES")
        self.assertEqual(out["side"], "BUY")
        # 0.555 rounds to 0.56 at the default 0.01 tick
        self.assertAlmostEqual(out["price"], 0.56, places=2)
        self.assertEqual(out["size_usd"], 100.0)
        self.assertEqual(out["reasoning"], "thoughtful entry")

    def test_place_limit_clamps_price_above_one(self):
        out = parse_tool_call(_tc(
            "place_limit_order",
            outcome="NO", side="SELL", price=5.0, size_usd=10,
        ))
        self.assertLessEqual(out["price"], 1.0)

    def test_place_market_zero_price(self):
        out = parse_tool_call(_tc(
            "place_market_order",
            outcome="YES", side="BUY", size_usd=42,
        ))
        self.assertEqual(out["order_type"], "MARKET")
        self.assertEqual(out["price"], 0.0)
        self.assertEqual(out["size_usd"], 42.0)

    def test_cancel_zero_size(self):
        out = parse_tool_call(_tc(
            "cancel_orders", outcome="YES", side="BUY",
        ))
        self.assertEqual(out["order_type"], "CANCEL")
        self.assertEqual(out["size_usd"], 0.0)

    def test_split_uses_size_usd(self):
        out = parse_tool_call(_tc("split_position", size_usd=50))
        self.assertEqual(out["order_type"], "SPLIT")
        self.assertEqual(out["size_usd"], 50.0)
        # SPLIT ignores outcome/side/price
        self.assertEqual(out["price"], 0.0)

    def test_merge_uses_size_pairs(self):
        out = parse_tool_call(_tc("merge_position", size_pairs=10))
        self.assertEqual(out["order_type"], "MERGE")
        self.assertEqual(out["size_usd"], 10.0)

    def test_negative_size_clamped_to_zero(self):
        out = parse_tool_call(_tc(
            "place_market_order",
            outcome="YES", side="BUY", size_usd=-5,
        ))
        self.assertEqual(out["size_usd"], 0.0)

    def test_invalid_outcome_falls_back_to_yes(self):
        out = parse_tool_call(_tc(
            "place_limit_order",
            outcome="MAYBE", side="BUY", price=0.5, size_usd=10,
        ))
        self.assertEqual(out["outcome"], "YES")

    def test_invalid_side_falls_back_to_buy(self):
        out = parse_tool_call(_tc(
            "place_limit_order",
            outcome="YES", side="HOLD", price=0.5, size_usd=10,
        ))
        self.assertEqual(out["side"], "BUY")

    def test_arguments_as_json_string(self):
        # Defensive: some clients send arguments as raw JSON string.
        out = parse_tool_call({
            "id": "x", "name": "place_market_order",
            "arguments": '{"outcome":"NO","side":"SELL","size_usd":7}',
        })
        self.assertEqual(out["order_type"], "MARKET")
        self.assertEqual(out["outcome"], "NO")
        self.assertEqual(out["size_usd"], 7.0)


if __name__ == "__main__":
    unittest.main()
