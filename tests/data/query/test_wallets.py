from __future__ import annotations

import datetime as dt
import unittest

from data.query import wallets as q
from tests.data._stub_ch import StubCH


class ListWalletsTest(unittest.TestCase):
    def test_returns_addresses(self):
        ch = StubCH({
            "SELECT DISTINCT proxy_wallet": [("0xa",), ("0xb",)],
        })
        out = q.list_wallets_in_market("0xCID", ch=ch)
        self.assertEqual(out, ["0xa", "0xb"])


class PreEventTradesTest(unittest.TestCase):
    def test_passes_cutoff(self):
        ch = StubCH({
            "FROM polymetl.dataapi_trades": [
                ("0xA", 0, 0.5, 100, dt.datetime(2025, 1, 1)),
            ],
        })
        rows = q.get_pre_event_trades("0xab", 1_700_000_000, ch=ch)
        self.assertEqual(len(rows), 1)
        self.assertEqual(ch.client.calls[0][1]["c"], 1_700_000_000)


class ResolvedOutcomesTest(unittest.TestCase):
    def test_empty_input(self):
        ch = StubCH({})
        self.assertEqual(q.get_resolved_outcomes([], ch=ch), {})

    def test_maps_winning_idx(self):
        ch = StubCH({
            "FROM polymetl.markets_resolved": [("A", 0), ("B", 1)],
        })
        out = q.get_resolved_outcomes(["A", "B"], ch=ch)
        self.assertEqual(out, {"A": 0, "B": 1})


class CapitalBoundsTest(unittest.TestCase):
    def test_returns_quantiles(self):
        ch = StubCH({
            "FROM polymetl.wallet_features": [(50.0, 5000.0)],
        })
        floor, cap = q.empirical_capital_bounds("0xCID", ch=ch)
        self.assertEqual((floor, cap), (50.0, 5000.0))


if __name__ == "__main__":
    unittest.main()
