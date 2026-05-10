"""parse_decision edge cases — JSON validation invariants."""
from __future__ import annotations

import json
import unittest

from agent.decision.parser import parse_decision, round_to_tick


class ParseDecisionTest(unittest.TestCase):
    def test_basic_limit_order(self):
        text = json.dumps({
            "order_type": "LIMIT", "outcome": "YES", "side": "BUY",
            "price": 0.55, "size_usd": 100.0, "reasoning": "ok",
        })
        out = parse_decision(text)
        self.assertEqual(out["order_type"], "LIMIT")
        self.assertEqual(out["outcome"], "YES")
        self.assertEqual(out["price"], 0.55)

    def test_strips_code_fences(self):
        text = "```json\n" + json.dumps({"order_type": "HOLD"}) + "\n```"
        out = parse_decision(text)
        self.assertEqual(out["order_type"], "HOLD")
        self.assertEqual(out["size_usd"], 0.0)

    def test_clamps_price_to_unit(self):
        text = json.dumps({"order_type": "LIMIT", "price": 5.0, "size_usd": 1})
        out = parse_decision(text)
        self.assertLessEqual(out["price"], 1.0)
        self.assertGreaterEqual(out["price"], 0.0)

    def test_invalid_order_type_raises(self):
        with self.assertRaises(ValueError):
            parse_decision(json.dumps({"order_type": "FROBNICATE"}))

    def test_negative_size_clamped_to_zero(self):
        text = json.dumps({"order_type": "MARKET", "size_usd": -5})
        self.assertEqual(parse_decision(text)["size_usd"], 0.0)

    def test_split_ignores_price_outcome(self):
        text = json.dumps({"order_type": "SPLIT", "size_usd": 50})
        out = parse_decision(text)
        self.assertEqual(out["price"], 0.0)
        self.assertEqual(out["size_usd"], 50.0)

    def test_no_json_object_raises(self):
        with self.assertRaises(ValueError):
            parse_decision("just plain text, no braces")


class RoundToTickTest(unittest.TestCase):
    def test_default_tick(self):
        self.assertAlmostEqual(round_to_tick(0.555), 0.56, places=2)

    def test_custom_tick(self):
        result = round_to_tick(0.5555, tick_size=0.001)
        self.assertIn(round(result, 4), (0.555, 0.556))

    def test_zero_tick_passthrough(self):
        self.assertEqual(round_to_tick(0.5, tick_size=0), 0.5)


if __name__ == "__main__":
    unittest.main()
