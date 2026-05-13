"""OpenAI function tool schemas — shape + completeness."""
from __future__ import annotations

import unittest

from agent.decision.tool_schemas import (
    NAME_TO_ORDER_TYPE, TOOL_SCHEMAS,
)


class ToolSchemaShapeTest(unittest.TestCase):
    def test_has_six_tools(self):
        # v13 (AGT-4) added `update_belief`; bumped from 5 → 6.
        self.assertEqual(len(TOOL_SCHEMAS), 6)

    def test_names_match_dispatcher(self):
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        self.assertEqual(names, set(NAME_TO_ORDER_TYPE))

    def test_order_types_are_engine_compatible(self):
        # Every order_type the parser maps to must be one the engine accepts.
        from environment.env import _execute_decision  # noqa: F401
        from agent.decision.parser import VALID_ORDER_TYPES
        for order_type in NAME_TO_ORDER_TYPE.values():
            self.assertIn(order_type, VALID_ORDER_TYPES)

    def test_each_tool_has_function_object(self):
        for t in TOOL_SCHEMAS:
            self.assertEqual(t["type"], "function")
            self.assertIn("function", t)
            self.assertIn("name", t["function"])
            self.assertIn("description", t["function"])
            self.assertIn("parameters", t["function"])

    def test_param_objects_are_typed(self):
        for t in TOOL_SCHEMAS:
            params = t["function"]["parameters"]
            self.assertEqual(params["type"], "object")
            self.assertIn("properties", params)
            self.assertIn("required", params)

    def test_limit_order_has_price_bounds(self):
        limit = next(t for t in TOOL_SCHEMAS
                     if t["function"]["name"] == "place_limit_order")
        price = limit["function"]["parameters"]["properties"]["price"]
        self.assertEqual(price["type"], "number")
        self.assertEqual(price["minimum"], 0.01)
        self.assertEqual(price["maximum"], 0.99)


if __name__ == "__main__":
    unittest.main()
