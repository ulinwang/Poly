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
        calls = []

        def fake_llm(**kwargs):
            calls.append(kwargs)
            names = {t["function"]["name"] for t in kwargs["tools"]}
            if names == {"update_belief"}:
                return {
                    "tool_call": {
                        "id": "tc_belief",
                        "name": "update_belief",
                        "arguments": {
                            "yes_prob": 0.57, "confidence": 0.6,
                            "rationale": "book is below my fair value",
                        },
                    },
                    "tool_calls": [{
                        "id": "tc_belief",
                        "name": "update_belief",
                        "arguments": {
                            "yes_prob": 0.57, "confidence": 0.6,
                            "rationale": "book is below my fair value",
                        },
                    }],
                    "text": "",
                    "raw": "{\"stage\":\"belief\"}",
                    "prompt_tokens": 10, "completion_tokens": 5,
                }
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
                "raw": "{\"stage\":\"trade\"}",
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
        self.assertIsNotNone(d.belief_update)
        self.assertAlmostEqual(d.belief_update["yes_prob"], 0.57)
        self.assertEqual(d.api_error, "")
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [t["function"]["name"] for t in calls[0]["tools"]],
            ["update_belief"],
        )
        self.assertNotIn(
            "update_belief",
            {t["function"]["name"] for t in calls[1]["tools"]},
        )

    def test_no_tool_call_is_hold(self):
        calls = []

        def fake_llm(**kwargs):
            calls.append(kwargs)
            names = {t["function"]["name"] for t in kwargs["tools"]}
            if names == {"update_belief"}:
                return {
                    "tool_call": {
                        "id": "tc_belief",
                        "name": "update_belief",
                        "arguments": {
                            "yes_prob": 0.45, "confidence": 0.5,
                            "rationale": "no meaningful change",
                        },
                    },
                    "text": "",
                    "raw": "{\"stage\":\"belief\"}",
                    "prompt_tokens": 0, "completion_tokens": 0,
                }
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
        self.assertIsNotNone(d.belief_update)
        self.assertEqual(len(calls), 2)

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


class MultiToolPerTurnTest(unittest.TestCase):
    """The model may emit several tool calls in one turn (parallel tool
    calling). The trade-stage loop must process them ALL in that turn —
    appending one assistant message listing every call plus a tool result
    for each — rather than handling only the first and dropping the rest."""

    def _belief(self):
        c = {"id": "b", "name": "update_belief",
             "arguments": {"yes_prob": 0.3, "confidence": 0.5,
                           "rationale": "r"}}
        return {"tool_call": c, "tool_calls": [c], "text": "",
                "raw": "{}", "prompt_tokens": 0, "completion_tokens": 0}

    def test_info_and_forum_post_in_one_turn(self):
        import agent.decision.runtime as rt
        from agent.decision.tool_schemas import select_tools
        from agent.info import SearchResult
        from environment.forum import Forum

        orig_search = rt.search_web
        rt.search_web = lambda query, backend=None, max_results=5: [
            SearchResult(title="Odds", snippet="France 16%", url="http://x")
        ]
        try:
            continues = {"n": 0}

            def call_fn(**kw):
                names = {t["function"]["name"] for t in kw["tools"]}
                if names == {"update_belief"}:
                    return self._belief()
                # First trade call: TWO continuing tools in one turn.
                return {
                    "tool_call": {"id": "i", "name": "get_information",
                                  "arguments": {"query": "france odds"}},
                    "tool_calls": [
                        {"id": "i", "name": "get_information",
                         "arguments": {"query": "france odds"}},
                        {"id": "p", "name": "post_to_forum",
                         "arguments": {"content": "France looks weak."}},
                    ],
                    "text": "", "reasoning_content": "search and post",
                    "raw": "{}", "prompt_tokens": 0, "completion_tokens": 0,
                }

            def continue_fn(**kw):
                continues["n"] += 1
                c = {"id": "t", "name": "place_market_order",
                     "arguments": {"outcome": "NO", "side": "BUY",
                                   "size_usd": 30}}
                return {"tool_call": c, "tool_calls": [c], "text": "",
                        "raw": "{}", "prompt_tokens": 0, "completion_tokens": 0}

            forum = Forum()
            infos, actions = [], []
            d = decide(
                persona=_persona(), question="Q?", description="R",
                end_date="2026", market=_market(), agent=_agent_state(),
                api_key="x", base_url="x", model="x",
                call_fn=call_fn, continue_fn=continue_fn,
                tools=select_tools(info_enabled=True, forum_enabled=True),
                info_enabled=True, forum_enabled=True, forum=forum,
                agent_id=1, tick=1,
                on_info_query=lambda q, r: infos.append(q),
                on_forum_action=lambda k, p: actions.append(k),
                max_attempts=1,
            )

            # Both tools handled in ONE turn => exactly one continuation call.
            self.assertEqual(continues["n"], 1)
            self.assertEqual(infos, ["france odds"])
            self.assertEqual(actions, ["post"])
            self.assertEqual(len(forum.posts), 1)
            # The continuation's trade tool is the final decision.
            self.assertEqual(d.order_type, "MARKET")
            self.assertEqual(d.outcome, "NO")
            self.assertEqual(d.size_usd, 30.0)
            self.assertEqual(d.api_error, "")
        finally:
            rt.search_web = orig_search


if __name__ == "__main__":
    unittest.main()
