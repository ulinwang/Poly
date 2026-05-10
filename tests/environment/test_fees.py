from __future__ import annotations

import unittest

from environment.fees import taker_fee


class TakerFeeTest(unittest.TestCase):
    def test_zero_fee_zero_bps(self):
        self.assertEqual(taker_fee(100, 0.5, 0.0), 0.0)

    def test_symmetric_around_half(self):
        # Fee at p=0.4 should equal fee at p=0.6 (symmetry of p(1-p)).
        f1 = taker_fee(100, 0.4, 100.0)
        f2 = taker_fee(100, 0.6, 100.0)
        self.assertAlmostEqual(f1, f2, places=8)

    def test_zero_at_extremes(self):
        # At p=0.01 or p=0.99 fee → ~0 (paper §2.1 economic intent).
        self.assertLess(taker_fee(100, 0.01, 100.0), 0.01)
        self.assertLess(taker_fee(100, 0.99, 100.0), 0.01)

    def test_max_at_half(self):
        # Maximum of p(1-p) is at p=0.5.
        max_p = taker_fee(100, 0.5, 100.0)
        for p in (0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9):
            self.assertGreaterEqual(max_p, taker_fee(100, p, 100.0))


if __name__ == "__main__":
    unittest.main()
