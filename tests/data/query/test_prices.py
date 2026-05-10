from __future__ import annotations

import unittest

from data.query import prices as q
from tests.data._stub_ch import StubCH


class FirstWindowAvgTest(unittest.TestCase):
    def test_normal(self):
        ch = StubCH({"FROM polymetl.clob_prices_history": [(50, 0.42)]})
        out = q.first_window_avg("TYES", 1_700_000_000, ch=ch)
        self.assertEqual(out["source"], "clob_prices_history")
        self.assertAlmostEqual(out["vwap"], 0.42)

    def test_no_rows_returns_none(self):
        ch = StubCH({"FROM polymetl.clob_prices_history": [(0, None)]})
        self.assertIsNone(q.first_window_avg("TYES", 1_700_000_000, ch=ch))


if __name__ == "__main__":
    unittest.main()
