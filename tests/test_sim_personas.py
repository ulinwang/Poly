from __future__ import annotations

import unittest

from src.sim import personas


class PersonaTest(unittest.TestCase):
    def test_three_default_personas_distinct(self):
        types = {p.persona_type for p in personas.DEFAULT_PERSONAS}
        self.assertEqual(types, {"SkepticalEngineer", "LotteryPlayer", "HerdFollower"})

    def test_risk_aversion_in_range(self):
        for p in personas.DEFAULT_PERSONAS:
            self.assertGreaterEqual(p.risk_aversion, 0.0)
            self.assertLessEqual(p.risk_aversion, 1.0)

    def test_assign_round_robin(self):
        out = personas.assign_personas(10, personas.DEFAULT_PERSONAS)
        self.assertEqual(len(out), 10)
        # 10 / 3 = 4 SkepticalEngineer, 3 each of others
        from collections import Counter
        c = Counter(p.persona_type for p in out)
        self.assertEqual(c["SkepticalEngineer"], 4)
        self.assertEqual(c["LotteryPlayer"], 3)
        self.assertEqual(c["HerdFollower"], 3)


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
