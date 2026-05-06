from __future__ import annotations

import unittest

from src.sim import lmsr


class LmsrPriceTest(unittest.TestCase):
    def test_initial_price_is_half(self):
        self.assertAlmostEqual(lmsr.price_yes(0, 0, 200), 0.5, places=6)
        self.assertAlmostEqual(lmsr.price_no(0, 0, 200), 0.5, places=6)

    def test_yes_no_sum_to_one(self):
        for q_yes, q_no, b in [(0, 0, 200), (50, 0, 200), (0, 100, 100), (250, 30, 50)]:
            self.assertAlmostEqual(
                lmsr.price_yes(q_yes, q_no, b) + lmsr.price_no(q_yes, q_no, b),
                1.0, places=8,
                msg=f"q_yes={q_yes} q_no={q_no} b={b}",
            )

    def test_yes_inventory_raises_yes_price(self):
        # If the AMM has sold YES shares (q_yes high), YES price is high
        self.assertGreater(lmsr.price_yes(100, 0, 200), 0.5)
        self.assertLess(lmsr.price_yes(0, 100, 200), 0.5)


class LmsrCostTest(unittest.TestCase):
    def test_cost_to_buy_positive(self):
        self.assertGreater(lmsr.cost_to_buy("YES", 50, 0, 0, 200), 0)

    def test_cost_to_buy_monotonic_in_shares(self):
        c1 = lmsr.cost_to_buy("YES", 10, 0, 0, 200)
        c2 = lmsr.cost_to_buy("YES", 20, 0, 0, 200)
        c3 = lmsr.cost_to_buy("YES", 50, 0, 0, 200)
        self.assertLess(c1, c2)
        self.assertLess(c2, c3)

    def test_buying_then_selling_is_close_to_zero(self):
        # Buy 50 YES, then sell back via negative
        c_buy = lmsr.cost_to_buy("YES", 50, 0, 0, 200)
        c_sell = lmsr.cost_to_buy("YES", -50, 50, 0, 200)
        # cost_to_buy returns positive when buying; negative shares = sell
        # so c_sell should be -c_buy
        self.assertAlmostEqual(c_buy + c_sell, 0.0, places=6)

    def test_invalid_side_raises(self):
        with self.assertRaises(ValueError):
            lmsr.cost_to_buy("BOTH", 1, 0, 0, 200)

    def test_buying_no_with_yes_inventory_is_cheaper(self):
        # When AMM has lots of YES (so YES price high), buying NO is
        # cheaper than buying NO from a fresh AMM.
        c_no_fresh = lmsr.cost_to_buy("NO", 50, 0, 0, 200)
        c_no_after_yes = lmsr.cost_to_buy("NO", 50, 100, 0, 200)
        self.assertLess(c_no_after_yes, c_no_fresh)


class SharesForBudgetTest(unittest.TestCase):
    def test_zero_budget_returns_zero(self):
        self.assertEqual(lmsr.shares_for_budget("YES", 0, 0, 0, 200), 0.0)
        self.assertEqual(lmsr.shares_for_budget("YES", -10, 0, 0, 200), 0.0)

    def test_round_trip(self):
        # Find shares for $50, then verify the cost is ~$50
        s = lmsr.shares_for_budget("YES", 50, 0, 0, 200)
        self.assertGreater(s, 0)
        c = lmsr.cost_to_buy("YES", s, 0, 0, 200)
        self.assertAlmostEqual(c, 50.0, places=3)


if __name__ == "__main__":
    unittest.main()
