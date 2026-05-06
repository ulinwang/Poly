from __future__ import annotations

import random
import unittest

from src.sim import initialization as init


class SignalSigmaTest(unittest.TestCase):
    def test_high_accuracy_tight_sigma(self):
        # past_accuracy = 1.0 → sigma should clip at the lower bound 0.05
        self.assertEqual(init.derive_signal_sigma(1.0), 0.05)

    def test_zero_accuracy_wide_sigma(self):
        # past_accuracy = 0.0 → 0.4 * 1.0 = 0.4 (the upper bound)
        self.assertAlmostEqual(init.derive_signal_sigma(0.0), 0.4)

    def test_mid_accuracy(self):
        # 0.5 acc → 0.4 * 0.5 = 0.2
        self.assertAlmostEqual(init.derive_signal_sigma(0.5), 0.2)

    def test_negative_accuracy_clipped(self):
        # Defensive: would compute 0.4 * 1.5 = 0.6 → clipped to 0.4
        self.assertEqual(init.derive_signal_sigma(-0.5), 0.4)


class RiskAversionTest(unittest.TestCase):
    def test_no_maker_no_holding(self):
        self.assertAlmostEqual(init.derive_risk_aversion(0.0, 0.0), 0.0)

    def test_full_maker_long_hold(self):
        # maker_ratio=1, holding=24h → 0.5 + 0.5*0.5 = 0.75
        out = init.derive_risk_aversion(1.0, 24.0)
        self.assertGreater(out, 0.5)
        self.assertLess(out, 1.0)

    def test_clamped_in_zero_one(self):
        for mr, h in [(0.0, 0.0), (1.0, 1000.0), (0.5, 12.0)]:
            v = init.derive_risk_aversion(mr, h)
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)


class DrawPrivateSignalTest(unittest.TestCase):
    def test_within_bounds(self):
        rng = random.Random(0)
        for _ in range(50):
            s = init.draw_private_signal(0.5, 0.2, rng)
            self.assertGreater(s, 0.01)
            self.assertLess(s, 0.99)

    def test_deterministic_with_same_seed(self):
        a = init.draw_private_signal(0.3, 0.1, random.Random(42))
        b = init.draw_private_signal(0.3, 0.1, random.Random(42))
        self.assertEqual(a, b)

    def test_extreme_mu_clamps(self):
        # If mu is at the boundary and sigma tiny, fallback path returns mu clipped
        rng = random.Random(0)
        s = init.draw_private_signal(0.5, 0.0, rng)
        self.assertGreater(s, 0.01)


class AgentInitDataclassTest(unittest.TestCase):
    def test_construction(self):
        a = init.AgentInit(
            wallet_addr="0xabc", persona_type="Calibrated",
            capital_initial=500.0,
            profile_text="You typically place limit orders.",
            private_signal_mu=0.4, private_signal_sigma=0.2,
            risk_aversion=0.5,
            src_tx_count=20, src_maker_ratio=0.6,
            src_avg_position_usd=25.0, src_asset_diversity=4,
        )
        self.assertEqual(a.wallet_addr, "0xabc")
        self.assertEqual(a.persona_type, "Calibrated")
        # Frozen → can't mutate
        with self.assertRaises(Exception):
            a.capital_initial = 1.0  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
