from __future__ import annotations

import datetime as dt
import json
import unittest
from typing import Any

from src import agent


SAMPLE_MARKET_ROW = (
    "12345",                                         # market_id
    "will-trump-win-2024",                           # slug
    "Will Donald Trump win the 2024 US election?",  # question
    "Resolves YES if Trump wins.",                   # description
    ["Yes", "No"],                                   # outcomes
    [1.0, 0.0],                                      # outcome_prices (resolved YES)
    1_500_000_000.0,                                 # volume
    dt.datetime(2024, 11, 5),                        # end_date
    1,                                               # closed
)


class PromptTest(unittest.TestCase):
    def test_user_prompt_includes_basics(self):
        p = agent.build_user_prompt(
            "Will X happen?", "Some rules.", ["Yes", "No"],
            dt.datetime(2026, 12, 31),
        )
        self.assertIn("Will X happen?", p)
        self.assertIn("Some rules.", p)
        self.assertIn("2026-12-31", p)
        self.assertIn("Yes, No", p)

    def test_user_prompt_truncates_long_description(self):
        long = "x" * 5000
        p = agent.build_user_prompt("q?", long, ["Yes", "No"], None)
        self.assertIn("[truncated]", p)
        self.assertLess(len(p), 3000)


class ParseResponseTest(unittest.TestCase):
    def test_clean_json(self):
        out = agent.parse_response('{"yes_probability": 0.42, "confidence": "Medium", "reasoning": "x."}')
        self.assertEqual(out["yes_probability"], 0.42)
        self.assertEqual(out["confidence"], "medium")
        self.assertEqual(out["reasoning"], "x.")

    def test_with_markdown_fence(self):
        s = '```json\n{"yes_probability": 0.7, "confidence": "high", "reasoning": "ok"}\n```'
        out = agent.parse_response(s)
        self.assertEqual(out["yes_probability"], 0.7)

    def test_with_prose_around(self):
        s = 'Sure! Here is my answer:\n{"yes_probability": 0.1, "confidence": "low", "reasoning": "..."}\nThanks.'
        out = agent.parse_response(s)
        self.assertEqual(out["yes_probability"], 0.1)

    def test_missing_probability_raises(self):
        with self.assertRaises(ValueError):
            agent.parse_response('{"confidence": "high"}')

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            agent.parse_response('{"yes_probability": 1.5, "confidence": "high", "reasoning": ""}')

    def test_no_json_raises(self):
        with self.assertRaises(ValueError):
            agent.parse_response("just prose")


class ResolvedYesTest(unittest.TestCase):
    def test_yes_resolved(self):
        self.assertEqual(agent._resolved_yes([1.0, 0.0], 1), 1)

    def test_no_resolved(self):
        self.assertEqual(agent._resolved_yes([0.0, 1.0], 1), 0)

    def test_active_market(self):
        self.assertIsNone(agent._resolved_yes([0.6, 0.4], 0))

    def test_partial_resolution(self):
        # 50/50 explicit unresolved
        self.assertIsNone(agent._resolved_yes([0.5, 0.5], 1))


class PredictOneTest(unittest.TestCase):
    def test_happy_path(self):
        def fake_call(**kwargs):
            return {
                "text": '{"yes_probability": 0.81, "confidence": "high", "reasoning": "trends favor"}',
                "prompt_tokens": 200,
                "completion_tokens": 30,
                "raw": '{"choices": [...]}',
            }

        fixed_now = dt.datetime(2026, 5, 6, 12, 0, 0)
        row = agent.predict_one(
            market_row=SAMPLE_MARKET_ROW,
            api_key="fake",
            base_url="https://x",
            model="deepseek-v4-flash",
            call_fn=fake_call,
            now_fn=lambda: fixed_now,
        )
        # Schema: 16 columns
        self.assertEqual(len(row), 16)
        # market_id
        self.assertEqual(row[1], "12345")
        # model + prompt_version
        self.assertEqual(row[2], "deepseek-v4-flash")
        self.assertEqual(row[3], "v1")
        # parsed prediction
        self.assertAlmostEqual(row[4], 0.81)
        self.assertEqual(row[5], "high")
        # market snapshot
        self.assertAlmostEqual(row[10], 1.0)            # yes price
        self.assertEqual(row[11], 1)                    # resolved YES
        self.assertAlmostEqual(row[12], 1.5e9)          # volume
        # bookkeeping
        self.assertEqual(row[14], "")                   # no error
        self.assertEqual(row[15], fixed_now)

    def test_http_error_captured(self):
        import urllib.error

        def boom(**kwargs):
            raise urllib.error.HTTPError("u", 500, "Server", {}, None)

        row = agent.predict_one(
            market_row=SAMPLE_MARKET_ROW,
            api_key="fake",
            base_url="https://x",
            model="m",
            call_fn=boom,
        )
        self.assertEqual(row[4], 0.0)
        self.assertTrue(row[14].startswith("http:"))

    def test_parse_error_captured(self):
        def bad(**kwargs):
            return {"text": "not json", "prompt_tokens": 1, "completion_tokens": 1, "raw": ""}

        row = agent.predict_one(
            market_row=SAMPLE_MARKET_ROW,
            api_key="fake",
            base_url="https://x",
            model="m",
            call_fn=bad,
        )
        self.assertTrue(row[14].startswith("parse:"))


class FakeClickHouse:
    def __init__(self, market_rows):
        self.market_rows = market_rows
        self.predictions_schema_called = False
        self.inserted: list[tuple] = []

    def ensure_predictions_schema(self):
        self.predictions_schema_called = True

    def insert_predictions(self, rows):
        self.inserted.extend(rows)

    def fetch_markets_for_prediction(self, **kwargs):
        return list(self.market_rows[: kwargs.get("limit", 20)])


class RunTest(unittest.TestCase):
    def test_run_dry_run_no_api_calls(self):
        # dry_run path should not call call_deepseek and should not insert
        original_settings = agent.get_settings

        class FakeSettings:
            DEEPSEEK_API_KEY = ""
            DEEPSEEK_BASE_URL = "https://x"
            DEEPSEEK_MODEL = "m"
            DEEPSEEK_TEMPERATURE = 0.0
            DEEPSEEK_TIMEOUT = 60.0

        agent.get_settings = lambda: FakeSettings()
        try:
            ch = FakeClickHouse([SAMPLE_MARKET_ROW])
            n = agent.run(limit=1, dry_run=True, ch=ch, skip_already_predicted=False)
        finally:
            agent.get_settings = original_settings
        self.assertEqual(n, 0)
        self.assertEqual(ch.inserted, [])
        self.assertTrue(ch.predictions_schema_called)


if __name__ == "__main__":
    unittest.main()
