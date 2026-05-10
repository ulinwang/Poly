from __future__ import annotations

import unittest

from data.query import orderbook as q
from tests.data._stub_ch import StubCH


class BootstrapPriorsTest(unittest.TestCase):
    def test_clob_path(self):
        ch = StubCH({
            "FROM polymetl.clob_orderbook": [(0.40, 0.44, 250.0)],
        })
        out = q.bootstrap_priors("TYES", 1_700_000_000, ch=ch)
        self.assertEqual(out["source"], "clob_orderbook")
        self.assertAlmostEqual(out["anchor_yes"], 0.42)
        self.assertAlmostEqual(out["spread"], 0.04)

    def test_no_book_returns_none(self):
        ch = StubCH({
            "FROM polymetl.clob_orderbook": [(None, None, 0.0)],
        })
        self.assertIsNone(q.bootstrap_priors("TYES", 1_700_000_000, ch=ch))


if __name__ == "__main__":
    unittest.main()
