from __future__ import annotations

import datetime as dt
import unittest

from data.query import trades as q
from tests.data._stub_ch import StubCH


class MarketOpenTsTest(unittest.TestCase):
    def test_uses_first_trade(self):
        first = dt.datetime(2025, 9, 9, 18, 56, 56)
        ch = StubCH({"FROM polymetl.dataapi_trades": [(first,)]})
        out = q.market_open_ts("0xCID", ch=ch)
        self.assertEqual(out, int(first.timestamp()))

    def test_no_trades_raises(self):
        ch = StubCH({"FROM polymetl.dataapi_trades": [(None,)]})
        with self.assertRaises(SystemExit):
            q.market_open_ts("0xCID", ch=ch)


class FirstWindowVwapTest(unittest.TestCase):
    def test_normal_path(self):
        ch = StubCH({"FROM polymetl.dataapi_trades": [(10, 4.0, 10.0)]})
        out = q.first_window_vwap("0xCID", 0, 1_700_000_000, ch=ch)
        self.assertAlmostEqual(out["vwap"], 0.4)
        self.assertEqual(out["source"], "dataapi_trades")

    def test_no_data_falls_back(self):
        ch = StubCH({"FROM polymetl.dataapi_trades": [(0, 0.0, 0.0)]})
        out = q.first_window_vwap("0xCID", 0, 1_700_000_000, ch=ch)
        self.assertEqual(out["vwap"], 0.5)
        self.assertEqual(out["source"], "fallback_0.5")


class TradeDispersionTest(unittest.TestCase):
    def test_returns_quantiles(self):
        ch = StubCH({
            "FROM polymetl.dataapi_trades": [(20, 0.5, 0.4, 0.6, 100.0)],
        })
        out = q.trade_dispersion("0xCID", 0, 1_700_000_000, ch=ch)
        self.assertEqual(out["n"], 20)
        self.assertAlmostEqual(out["q25"], 0.4)
        self.assertAlmostEqual(out["q75"], 0.6)


if __name__ == "__main__":
    unittest.main()
