"""Bio sanitization + LLM call shape for calibrated personas."""
from __future__ import annotations

import unittest

from agent.personas import calibrated as pg


SAMPLE_FEATURES = {
    "capital_usd": 1500.0, "tx_count": 42, "maker_ratio": 0.0,
    "avg_position_usd": 35.7, "asset_diversity": 8,
    "avg_holding_h": 0.0, "past_accuracy": 0.55, "n_resolved_prior": 9,
}


class SanitizeBioTest(unittest.TestCase):
    def test_strips_role_labels(self):
        bio = "I'm a professional market maker and crypto whale on Polymarket."
        out = pg.sanitize_bio(bio)
        self.assertNotIn("market maker", out.lower())
        self.assertNotIn("whale", out.lower())
        self.assertIn(pg._BIO_REDACTED, out)

    def test_empty_returns_empty(self):
        self.assertEqual(pg.sanitize_bio(""), "")
        self.assertEqual(pg.sanitize_bio(None), "")  # type: ignore[arg-type]


class UserPromptTest(unittest.TestCase):
    def test_omits_unreliable_fields(self):
        # maker_ratio + avg_holding_h are honest placeholders — must
        # not be promoted to factual claims in the prompt.
        out = pg._user_prompt(SAMPLE_FEATURES)
        self.assertNotIn("Maker", out)
        # Above the "Do not invent" line, no maker/holding mention.
        head = out.split("Do not invent")[0]
        self.assertNotIn("maker", head)
        self.assertNotIn("holding time", head)

    def test_includes_bio_when_provided(self):
        out = pg._user_prompt(SAMPLE_FEATURES, bio="loves NBA",
                               display_name="Alice")
        self.assertIn("loves NBA", out)
        self.assertIn("Alice", out)


class GenerateProfileTest(unittest.TestCase):
    def test_clean_response_ok(self):
        def fake_call(**kwargs):
            return {
                "text": "You trade modestly across 8 markets and have 55% "
                        "accuracy on resolved positions.",
                "raw": "",
            }
        text, ok = pg.generate_profile(
            SAMPLE_FEATURES, api_key="x", base_url="x", model="x",
            call_fn=fake_call,
        )
        self.assertTrue(ok)
        self.assertIn("modestly", text)

    def test_label_in_response_redacted(self):
        def fake_call(**kwargs):
            return {"text": "You are a market maker.", "raw": ""}
        text, ok = pg.generate_profile(
            SAMPLE_FEATURES, api_key="x", base_url="x", model="x",
            call_fn=fake_call,
        )
        self.assertNotIn("market maker", text.lower())
        self.assertTrue(ok)

    def test_call_failure_returns_not_ok(self):
        def boom(**kwargs):
            raise RuntimeError("network down")
        text, ok = pg.generate_profile(
            SAMPLE_FEATURES, api_key="x", base_url="x", model="x",
            call_fn=boom,
        )
        self.assertFalse(ok)
        self.assertTrue(text.startswith("[error:"))


if __name__ == "__main__":
    unittest.main()
