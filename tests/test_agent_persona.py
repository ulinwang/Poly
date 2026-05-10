"""v7: hardcoded archetypes deleted from src/agent/persona.py.

Persona is now a transparent dataclass; profile_text comes from
src.population.persona_generator (LLM-rendered from real wallet
features, see docs/EMPIRICAL_PRIORS.md).
"""
from __future__ import annotations

import unittest

from src.agent import persona as persona_mod
from src.agent.decision import round_to_tick


class PersonaDataclassTest(unittest.TestCase):
    def test_persona_holds_four_fields(self):
        p = persona_mod.Persona(
            persona_type="Calibrated",
            risk_aversion=0.5,
            capital_initial=1234.0,
            profile_text="trader who traded $50 across 7 markets at 60% accuracy",
        )
        self.assertEqual(p.persona_type, "Calibrated")
        self.assertEqual(p.risk_aversion, 0.5)
        self.assertEqual(p.capital_initial, 1234.0)
        self.assertIn("60%", p.profile_text)

    def test_persona_is_frozen(self):
        p = persona_mod.Persona("X", 0.5, 100.0, "p")
        with self.assertRaises(Exception):
            p.persona_type = "Y"  # type: ignore[misc]


class PromptTest(unittest.TestCase):
    def test_build_system_prompt_includes_question_and_persona(self):
        p = persona_mod.Persona(
            persona_type="Calibrated", risk_aversion=0.5,
            capital_initial=1000.0,
            profile_text="thoughtful, evidence-based trader",
        )
        out = persona_mod.build_system_prompt(
            p, "Will X happen?", "Rules.", "2026-12-31",
        )
        self.assertIn("evidence-based", out)
        self.assertIn("Will X happen?", out)
        self.assertIn("2026-12-31", out)

    def test_long_description_truncated(self):
        p = persona_mod.Persona("Calibrated", 0.5, 1000.0, "p")
        out = persona_mod.build_system_prompt(p, "q?", "x" * 5000, "2026-01-01")
        self.assertIn("[truncated]", out)


class RoundToTickTest(unittest.TestCase):
    def test_round_to_tick_default(self):
        self.assertAlmostEqual(round_to_tick(0.555), 0.56, places=2)

    def test_round_to_tick_finer(self):
        result = round_to_tick(0.5555, tick_size=0.001)
        self.assertIn(round(result, 4), (0.555, 0.556))

    def test_round_to_tick_zero_passthrough(self):
        self.assertEqual(round_to_tick(0.5, tick_size=0), 0.5)

    def test_round_to_tick_no_change_for_aligned(self):
        self.assertAlmostEqual(round_to_tick(0.50), 0.50, places=10)


if __name__ == "__main__":
    unittest.main()
