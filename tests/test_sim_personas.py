from __future__ import annotations

import unittest

from src.sim import personas
from src.sim.agent import round_to_tick


class PersonaTest(unittest.TestCase):
    def test_default_personas_distinct(self):
        types = {p.persona_type for p in personas.DEFAULT_PERSONAS}
        self.assertEqual(
            types,
            {"SkepticalEngineer", "LotteryPlayer", "HerdFollower", "MarketMaker"},
        )

    def test_risk_aversion_in_range(self):
        for p in personas.DEFAULT_PERSONAS:
            self.assertGreaterEqual(p.risk_aversion, 0.0)
            self.assertLessEqual(p.risk_aversion, 1.0)

    def test_assign_round_robin_with_4_personas(self):
        out = personas.assign_personas(12, personas.DEFAULT_PERSONAS)
        self.assertEqual(len(out), 12)
        # 12 / 4 personas = 3 of each
        from collections import Counter
        c = Counter(p.persona_type for p in out)
        for ptype in ("SkepticalEngineer", "LotteryPlayer", "HerdFollower", "MarketMaker"):
            self.assertEqual(c[ptype], 3)


class PromptTest(unittest.TestCase):
    def test_system_prompt_contains_persona(self):
        p = personas.SKEPTICAL_ENGINEER
        out = personas.build_system_prompt(p, "Will X happen?", "Rules.", "2026-12-31")
        self.assertIn("aerospace", out.lower())
        self.assertIn("Will X happen?", out)
        self.assertIn("2026-12-31", out)

    def test_long_description_truncated(self):
        out = personas.build_system_prompt(
            personas.LOTTERY_PLAYER, "q?", "x" * 5000, "2026-01-01",
        )
        self.assertIn("[truncated]", out)

    def test_market_maker_profile_mentions_split(self):
        self.assertIn("split", personas.MARKET_MAKER.profile_text.lower())


class RoundToTickTest(unittest.TestCase):
    def test_round_to_tick_default(self):
        self.assertAlmostEqual(round_to_tick(0.555), 0.56, places=2)

    def test_round_to_tick_finer(self):
        # 0.5555 / 0.001 = 555.5; round() uses banker's rounding => 556
        result = round_to_tick(0.5555, tick_size=0.001)
        self.assertIn(round(result, 4), (0.555, 0.556))

    def test_round_to_tick_zero_passthrough(self):
        self.assertEqual(round_to_tick(0.5, tick_size=0), 0.5)

    def test_round_to_tick_no_change_for_aligned(self):
        self.assertAlmostEqual(round_to_tick(0.50), 0.50, places=10)


if __name__ == "__main__":
    unittest.main()
