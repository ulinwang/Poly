from __future__ import annotations

import unittest

from agent.features.temporal import n_ticks_for_lifetime


class NTicksTest(unittest.TestCase):
    def test_clamps_floor(self):
        # Tiny 12h market → 12/6 = 2 ticks → clamped to 8
        self.assertEqual(
            n_ticks_for_lifetime(0, 12 * 3600), 8,
        )

    def test_clamps_cap(self):
        # 1000h market → 1000/6 ≈ 167 → clamped to 48
        self.assertEqual(
            n_ticks_for_lifetime(0, 1000 * 3600), 48,
        )

    def test_typical_window(self):
        # ~5-day market = 120h / 6h = 20 ticks
        self.assertEqual(
            n_ticks_for_lifetime(0, 120 * 3600), 20,
        )


if __name__ == "__main__":
    unittest.main()
