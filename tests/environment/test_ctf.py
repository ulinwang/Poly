from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from environment.ctf import split, merge


@dataclass
class _Agent:
    cash: float = 100.0
    yes_shares: float = 0.0
    no_shares: float = 0.0


class CtfSplitTest(unittest.TestCase):
    def test_split_creates_pair(self):
        a = _Agent(cash=100.0)
        pairs, err = split(a, 30.0)
        self.assertEqual(err, "")
        self.assertEqual(pairs, 30.0)
        self.assertEqual(a.cash, 70.0)
        self.assertEqual(a.yes_shares, 30.0)
        self.assertEqual(a.no_shares, 30.0)

    def test_split_capped_by_cash(self):
        a = _Agent(cash=10.0)
        pairs, _ = split(a, 100.0)
        self.assertEqual(pairs, 10.0)
        self.assertEqual(a.cash, 0.0)

    def test_split_zero_cash(self):
        a = _Agent(cash=0.0)
        pairs, err = split(a, 50.0)
        self.assertEqual(pairs, 0.0)
        self.assertEqual(err, "insufficient_cash")


class CtfMergeTest(unittest.TestCase):
    def test_merge_redeems_pair(self):
        a = _Agent(cash=0.0, yes_shares=20, no_shares=20)
        pairs, err = merge(a, 15.0)
        self.assertEqual(err, "")
        self.assertEqual(pairs, 15.0)
        self.assertEqual(a.cash, 15.0)
        self.assertEqual(a.yes_shares, 5)
        self.assertEqual(a.no_shares, 5)

    def test_merge_capped_by_min_held(self):
        a = _Agent(cash=0.0, yes_shares=20, no_shares=5)
        pairs, _ = merge(a, 50.0)
        self.assertEqual(pairs, 5.0)

    def test_merge_unmatched_pair_zero(self):
        a = _Agent(cash=0.0, yes_shares=10, no_shares=0)
        pairs, err = merge(a, 5.0)
        self.assertEqual(pairs, 0.0)
        self.assertEqual(err, "insufficient_pairs")


if __name__ == "__main__":
    unittest.main()
