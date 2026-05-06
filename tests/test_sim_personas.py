from __future__ import annotations

import unittest

from src.sim import personas


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


if __name__ == "__main__":
    unittest.main()
