from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.sim import persona_generator as pg


SAMPLE_FEATURES = {
    "capital_usd": 1500.0,
    "tx_count": 42,
    "maker_ratio": 0.6,
    "avg_position_usd": 35.7,
    "asset_diversity": 8,
    "avg_holding_h": 12.5,
    "past_accuracy": 0.55,
    "n_resolved_prior": 9,
}


class UserPromptTest(unittest.TestCase):
    def test_includes_reliable_facts(self):
        p = pg._user_prompt(SAMPLE_FEATURES)
        self.assertIn("$1,500", p)         # capital
        self.assertIn("42", p)             # tx_count
        self.assertIn("$35.70", p)         # avg position
        self.assertIn("55%", p)            # past_accuracy
        self.assertIn("9", p)              # n_resolved

    def test_omits_unreliable_fields(self):
        # maker_ratio and avg_holding_h are placeholders (0.0); the API
        # cannot extract them. We must NOT mention them in the prompt
        # or the LLM will fabricate "100% taker" / "0h holding" facts.
        p = pg._user_prompt(SAMPLE_FEATURES)
        self.assertNotIn("Maker", p)
        self.assertNotIn("maker", p.split("Do not")[0])  # no factual claim
        self.assertNotIn("holding time", p.split("Do not")[0])
        self.assertNotIn("60%", p)


class StripRoleLabelsTest(unittest.TestCase):
    def test_redacts_market_maker(self):
        out = pg._strip_role_labels("You are a market maker who quotes both sides.")
        self.assertNotIn("market maker", out.lower())
        self.assertIn("this trader", out)

    def test_redacts_whale_and_apex(self):
        out = pg._strip_role_labels("You are a whale and an apex predator.")
        self.assertNotIn("whale", out.lower())
        self.assertNotIn("apex", out.lower())
        self.assertNotIn("predator", out.lower())

    def test_clean_text_passes_through(self):
        clean = "You typically place limit orders, hold ~12 hours, and "\
                "have a 55% accuracy track record."
        self.assertEqual(pg._strip_role_labels(clean), clean)


class GenerateProfileTest(unittest.TestCase):
    def test_clean_response_returns_ok(self):
        def fake_call(**kwargs):
            return {
                "text": "You trade $35 on average across 8 markets, prefer "
                        "limit orders, and hold positions ~12h with 55% accuracy.",
                "raw": "",
            }
        text, ok = pg.generate_profile(
            SAMPLE_FEATURES, api_key="x", base_url="x", model="x",
            call_fn=fake_call,
        )
        self.assertTrue(ok)
        self.assertIn("limit", text)

    def test_label_in_response_redacted_and_flagged(self):
        def fake_call(**kwargs):
            return {
                "text": "You are a market maker quoting both sides for fun.",
                "raw": "",
            }
        text, ok = pg.generate_profile(
            SAMPLE_FEATURES, api_key="x", base_url="x", model="x",
            call_fn=fake_call,
        )
        # Cleanup makes it pass the regex (because we replaced it)
        self.assertNotIn("market maker", text.lower())
        # ok=True after redaction (forbidden labels gone post-cleanup)
        self.assertTrue(ok)
        self.assertIn("this trader", text)

    def test_call_failure_returns_error_not_ok(self):
        def boom(**kwargs):
            raise RuntimeError("network down")
        text, ok = pg.generate_profile(
            SAMPLE_FEATURES, api_key="x", base_url="x", model="x",
            call_fn=boom,
        )
        self.assertFalse(ok)
        self.assertTrue(text.startswith("[error:"))


class CacheIOTest(unittest.TestCase):
    def test_load_missing_returns_empty(self):
        out = pg.load_cache(Path("/nonexistent/nope.json"))
        self.assertEqual(out, {})

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cache.json"
            data = {"581883": {"0xabc": {"profile_text": "...", "ok": True}}}
            pg.save_cache(data, p)
            loaded = pg.load_cache(p)
            self.assertEqual(loaded, data)


if __name__ == "__main__":
    unittest.main()
