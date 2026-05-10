"""v7 — derive_priors.py unit tests with stub ClickHouse.

We don't go to a live DB. We feed `derive_priors` a fake CH whose
`client.execute` returns canned tuples per SQL substring, and verify:
  - JSON schema matches what runner.py + build_population expect
  - source-fallback hierarchy works (clob_orderbook → trades dispersion)
  - n_ticks bound logic respects the [8, 48] range
"""
from __future__ import annotations

import datetime as dt
import json
import unittest
from typing import Any
from unittest import mock

from src.population import derive_priors as dp


class _StubClient:
    def __init__(self, route_map: dict):
        self.route_map = route_map

    def execute(self, sql: str, params: Any = None) -> list:
        for substr, rows in self.route_map.items():
            if substr in sql:
                if callable(rows):
                    return rows(params or {})
                return rows
        raise AssertionError(f"unrouted SQL:\n{sql[:200]}")


class _StubCH:
    def __init__(self, route_map: dict):
        self.client = _StubClient(route_map)


def _slug_meta_route(params):
    return [(
        "0xCID", "spacex", json.dumps([
            {"token_id": "TYES", "outcome": "Yes"},
            {"token_id": "TNO", "outcome": "No"},
        ]),
        0.01,    # tick
        0.0,     # taker_base_fee
        dt.datetime(2025, 10, 14),
        dt.datetime(2025, 9, 10),
    )]


class FetchMarketMetaTest(unittest.TestCase):
    def test_resolves_yes_no_token_ids(self):
        ch = _StubCH({
            "FROM polymetl.clob_markets": _slug_meta_route,
            "FROM polymetl.markets_resolved": [(1, dt.datetime(2025, 10, 14), None)],
        })
        meta = dp.fetch_market_meta(ch, "spacex")
        self.assertEqual(meta["yes_token_id"], "TYES")
        self.assertEqual(meta["no_token_id"], "TNO")
        self.assertEqual(meta["winning_idx"], 1)
        self.assertEqual(meta["minimum_tick_size"], 0.01)


class MarketOpenTsTest(unittest.TestCase):
    def test_uses_first_trade_ts(self):
        first_ts = dt.datetime(2025, 9, 10, 12, 0, 0)
        ch = _StubCH({
            "FROM polymetl.dataapi_trades": [(first_ts,)],
        })
        out = dp.market_open_ts(ch, "0xCID")
        self.assertEqual(out, int(first_ts.timestamp()))

    def test_no_trades_raises(self):
        ch = _StubCH({"FROM polymetl.dataapi_trades": [(None,)]})
        with self.assertRaises(SystemExit):
            dp.market_open_ts(ch, "0xCID")


class FirstWindowVwapTest(unittest.TestCase):
    def test_clob_prices_history_preferred(self):
        ch = _StubCH({
            "FROM polymetl.clob_prices_history": [(50, 0.42)],
        })
        out = dp.first_window_vwap(ch, "0xCID", "TYES", 1_700_000_000)
        self.assertEqual(out["source"], "clob_prices_history")
        self.assertAlmostEqual(out["vwap"], 0.42)
        self.assertEqual(out["n_trades"], 50)

    def test_falls_back_to_dataapi_trades(self):
        # No prices_history rows, but trades available.
        ch = _StubCH({
            "FROM polymetl.clob_prices_history": [(0, None)],
            "FROM polymetl.clob_markets": [("0xCID",)],
            "FROM polymetl.dataapi_trades": [(10, 4.0, 10.0)],  # vwap=0.4
        })
        out = dp.first_window_vwap(ch, "0xCID", "TYES", 1_700_000_000)
        self.assertEqual(out["source"], "dataapi_trades")
        self.assertAlmostEqual(out["vwap"], 0.4)

    def test_no_data_falls_back_to_neutral(self):
        ch = _StubCH({
            "FROM polymetl.clob_prices_history": [(0, None)],
            "FROM polymetl.clob_markets": [("0xCID",)],
            "FROM polymetl.dataapi_trades": [(0, 0.0, 0.0)],
        })
        out = dp.first_window_vwap(ch, "0xCID", "TYES", 1_700_000_000)
        self.assertEqual(out["source"], "fallback_0.5")
        self.assertEqual(out["vwap"], 0.5)


class BootstrapBookPriorsTest(unittest.TestCase):
    def test_clob_orderbook_preferred(self):
        ch = _StubCH({
            "FROM polymetl.clob_orderbook": [(0.40, 0.44, 250.0)],
        })
        out = dp.bootstrap_book_priors(ch, "TYES", 1_700_000_000)
        self.assertEqual(out["source"], "clob_orderbook")
        self.assertAlmostEqual(out["anchor_yes"], 0.42)
        self.assertAlmostEqual(out["spread"], 0.04)
        self.assertEqual(out["depth_per_level"], 250.0)
        self.assertEqual(out["depth_levels"], 3)

    def test_fallback_to_trade_dispersion(self):
        ch = _StubCH({
            "FROM polymetl.clob_orderbook": [(None, None, 0.0)],
            "FROM polymetl.clob_markets": [("0xCID",)],
            "FROM polymetl.dataapi_trades": [(20, 0.5, 0.4, 0.6, 100.0)],
        })
        out = dp.bootstrap_book_priors(ch, "TYES", 1_700_000_000)
        self.assertEqual(out["source"], "dataapi_trades_dispersion")
        self.assertAlmostEqual(out["anchor_yes"], 0.5)
        self.assertAlmostEqual(out["spread"], 0.20)


class MarketLifetimeTickCountTest(unittest.TestCase):
    def test_clamps_to_min_8(self):
        # 12-hour market would compute 12/6=2 ticks, clamped to 8
        last = dt.datetime.utcfromtimestamp(1_700_000_000 + 12 * 3600)
        ch = _StubCH({"FROM polymetl.dataapi_trades": [(last,)]})
        out = dp.market_lifetime_n_ticks(ch, "0xCID", 1_700_000_000)
        self.assertEqual(out, 8)

    def test_clamps_to_max_48(self):
        # 1000-hour market = 1000/6 ≈ 167 → clamped to 48
        last = dt.datetime.utcfromtimestamp(1_700_000_000 + 1000 * 3600)
        ch = _StubCH({"FROM polymetl.dataapi_trades": [(last,)]})
        out = dp.market_lifetime_n_ticks(ch, "0xCID", 1_700_000_000)
        self.assertEqual(out, 48)


if __name__ == "__main__":
    unittest.main()
