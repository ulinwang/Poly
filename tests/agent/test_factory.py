"""init_agents() smoke tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent import factory
from agent.factory import (
    derive_signal_sigma, draw_private_signal, AgentInit, load_priors,
)
import random


class SignalSigmaTest(unittest.TestCase):
    def test_high_accuracy_tightens(self):
        s_high = derive_signal_sigma(0.9, scale=0.4, floor=0.05, cap=0.4)
        s_low = derive_signal_sigma(0.1, scale=0.4, floor=0.05, cap=0.4)
        self.assertLess(s_high, s_low)

    def test_floor_cap_enforced(self):
        s = derive_signal_sigma(1.0, scale=0.4, floor=0.05, cap=0.4)
        self.assertGreaterEqual(s, 0.05)
        s2 = derive_signal_sigma(-0.5, scale=0.4, floor=0.05, cap=0.4)
        self.assertLessEqual(s2, 0.4)


class DrawPrivateSignalTest(unittest.TestCase):
    def test_in_truncation_bounds(self):
        rng = random.Random(0)
        for _ in range(50):
            s = draw_private_signal(0.5, 0.2, rng)
            self.assertGreater(s, 0.01)
            self.assertLess(s, 0.99)

    def test_mean_preserved_at_extreme_mu(self):
        """Regression: the old truncated-normal inflated the realized
        mean to ~0.32 at mu=0.15, sigma=0.32 (handed every agent a
        bullish prior -> spurious upward price drift). The Beta draw
        must keep the realized mean within 0.02 of the intended mu
        even when mu is near a bound."""
        rng = random.Random(1)
        for mu in (0.15, 0.85):
            for sigma in (0.08, 0.20, 0.32, 0.38):
                draws = [draw_private_signal(mu, sigma, rng)
                         for _ in range(20000)]
                realized = sum(draws) / len(draws)
                self.assertAlmostEqual(
                    realized, mu, delta=0.02,
                    msg=f"mu={mu} sigma={sigma}: realized {realized:.3f}",
                )

    def test_zero_sigma_returns_mu(self):
        rng = random.Random(2)
        self.assertAlmostEqual(draw_private_signal(0.3, 0.0, rng), 0.3,
                               delta=1e-6)


class LoadPriorsTest(unittest.TestCase):
    def test_missing_file_raises(self):
        with self.assertRaises(SystemExit):
            load_priors("nope", data_dir=Path("/tmp/nope-not-real"))

    def test_loads_valid_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "priors_foo.json"
            p.write_text(json.dumps({"signal_mu": 0.5, "n_ticks": 24}))
            out = load_priors("foo", data_dir=Path(d))
            self.assertEqual(out["signal_mu"], 0.5)


class PersonaSetGuardTest(unittest.TestCase):
    def test_unsupported_persona_set_raises(self):
        with self.assertRaises(NotImplementedError):
            factory.init_agents("any-slug", persona_set="hand_coded")


if __name__ == "__main__":
    unittest.main()
