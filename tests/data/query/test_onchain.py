from __future__ import annotations

import unittest

from data.query import onchain as q


class OnchainScaffoldTest(unittest.TestCase):
    def test_get_onchain_fills_raises(self):
        with self.assertRaises(NotImplementedError):
            q.get_onchain_fills("0xCID")

    def test_get_onchain_redeems_raises(self):
        with self.assertRaises(NotImplementedError):
            q.get_onchain_redeems("0xCID")

    def test_get_onchain_splits_raises(self):
        with self.assertRaises(NotImplementedError):
            q.get_onchain_splits("0xCID")


if __name__ == "__main__":
    unittest.main()
