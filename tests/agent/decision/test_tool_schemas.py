"""OpenAI function tool schemas — shape + completeness."""
from __future__ import annotations

import unittest

from agent.decision.tool_schemas import (
    INFO_TOOL_NAME, FORUM_TOOL_NAMES, NAME_TO_ORDER_TYPE, TOOL_SCHEMAS,
    select_tools,
)


class SelectToolsTest(unittest.TestCase):
    def test_default_includes_belief(self):
        tools = select_tools()
        names = {t["function"]["name"] for t in tools}
        self.assertIn("update_belief", names)
        self.assertEqual(len(tools), len(TOOL_SCHEMAS))

    def test_disabled_drops_belief(self):
        tools = select_tools(belief_update_enabled=False)
        names = {t["function"]["name"] for t in tools}
        self.assertNotIn("update_belief", names)
        self.assertEqual(len(tools), len(TOOL_SCHEMAS) - 1)

    def test_default_includes_info(self):
        names = {t["function"]["name"] for t in select_tools()}
        self.assertIn(INFO_TOOL_NAME, names)

    def test_info_disabled_drops_info(self):
        tools = select_tools(info_enabled=False)
        names = {t["function"]["name"] for t in tools}
        self.assertNotIn(INFO_TOOL_NAME, names)
        self.assertEqual(len(tools), len(TOOL_SCHEMAS) - 1)


class ToolSchemaShapeTest(unittest.TestCase):
    def test_tool_count(self):
        # 5 order tools + update_belief (6) + get_information (7) + 4 forum
        # tools (read/post/comment/follow) = 11.
        self.assertEqual(len(TOOL_SCHEMAS), 11)

    def test_names_match_dispatcher(self):
        # `get_information` and the forum tools are READ/social tools, not
        # orders, so they are intentionally absent from NAME_TO_ORDER_TYPE.
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        non_order = {INFO_TOOL_NAME} | set(FORUM_TOOL_NAMES)
        self.assertEqual(names - non_order, set(NAME_TO_ORDER_TYPE))
        self.assertTrue(non_order.isdisjoint(NAME_TO_ORDER_TYPE))

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
