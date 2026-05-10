"""Unit tests for clob_api row-builder functions: market_to_row,
prices_history_to_rows, book_to_rows, quotes_to_rows."""
from __future__ import annotations

import datetime as dt
import json
import unittest

from data.sources.clob_api.puller import (
    market_to_row, prices_history_to_rows, book_to_rows, quotes_to_rows,
)


# Column order for clob_markets INSERT, mirrored from puller.insert_markets.
CLOB_MARKETS_COLUMNS = [
    "condition_id", "question_id", "question", "description", "market_slug",
    "enable_order_book", "active", "closed", "archived", "accepting_orders",
    "accepting_order_timestamp", "minimum_order_size", "minimum_tick_size",
    "neg_risk", "neg_risk_market_id", "neg_risk_request_id",
    "end_date_iso", "game_start_time", "seconds_delay",
    "maker_base_fee", "taker_base_fee", "fpmm", "is_50_50_outcome",
    "notifications_enabled", "icon", "image", "tags", "tokens_json",
    "rewards_min_size", "rewards_max_spread", "rewards_rates_json",
    "raw_json", "fetched_at",
]


class MarketToRowTests(unittest.TestCase):
    def setUp(self):
        self.fa = dt.datetime(2026, 5, 9, 12, 0, 0)

    def test_minimal_dict_produces_correct_column_count(self):
        row = market_to_row({}, self.fa)
        self.assertEqual(len(row), len(CLOB_MARKETS_COLUMNS))
        # raw_json column is JSON dump of input
        raw_json_idx = CLOB_MARKETS_COLUMNS.index("raw_json")
        self.assertEqual(row[raw_json_idx], "{}")
        # fetched_at is at the end
        self.assertEqual(row[-1], self.fa)

    def test_full_dict_field_mapping(self):
        m = {
            "condition_id": "0xabc",
            "question_id": "0xdef",
            "question": "will it rain?",
            "description": "rain",
            "market_slug": "rain-tomorrow",
            "enable_order_book": True,
            "active": False,
            "closed": True,
            "archived": False,
            "accepting_orders": True,
            "accepting_order_timestamp": "2026-05-09T00:00:00Z",
            "minimum_order_size": "5.0",
            "minimum_tick_size": "0.01",
            "neg_risk": True,
            "neg_risk_market_id": "nr1",
            "neg_risk_request_id": "nrr1",
            "end_date_iso": "2026-06-01T00:00:00Z",
            "game_start_time": "2026-05-15T00:00:00Z",
            "seconds_delay": "5",
            "maker_base_fee": 100,
            "taker_base_fee": 200,
            "fpmm": "0xfpmm",
            "is_50_50_outcome": False,
            "notifications_enabled": True,
            "icon": "ico",
            "image": "img",
            "tags": ["a", "b", 3],
            "tokens": [{"token_id": "T1", "outcome": "Yes"}],
            "rewards": {"min_size": 10, "max_spread": 0.05, "rates": [1, 2]},
        }
        row = market_to_row(m, self.fa)
        idx = CLOB_MARKETS_COLUMNS.index
        self.assertEqual(row[idx("condition_id")], "0xabc")
        self.assertEqual(row[idx("enable_order_book")], 1)
        self.assertEqual(row[idx("active")], 0)
        self.assertEqual(row[idx("closed")], 1)
        # tags coerced to strings
        self.assertEqual(row[idx("tags")], ["a", "b", "3"])
        # tokens dumped as JSON string
        self.assertEqual(json.loads(row[idx("tokens_json")]),
                         [{"token_id": "T1", "outcome": "Yes"}])
        # rewards.rates dumped as JSON string
        self.assertEqual(json.loads(row[idx("rewards_rates_json")]), [1, 2])
        self.assertAlmostEqual(row[idx("rewards_min_size")], 10.0)
        self.assertAlmostEqual(row[idx("rewards_max_spread")], 0.05)
        self.assertEqual(row[idx("seconds_delay")], 5)
        self.assertIsInstance(row[idx("end_date_iso")], dt.datetime)

    def test_missing_rewards_yields_zero_defaults(self):
        row = market_to_row({"condition_id": "0x"}, self.fa)
        idx = CLOB_MARKETS_COLUMNS.index
        self.assertEqual(row[idx("rewards_min_size")], 0.0)
        self.assertEqual(row[idx("rewards_max_spread")], 0.0)
        self.assertEqual(row[idx("rewards_rates_json")], "")

    def test_tags_default_empty_list(self):
        row = market_to_row({}, self.fa)
        self.assertEqual(row[CLOB_MARKETS_COLUMNS.index("tags")], [])


class PricesHistoryToRowsTests(unittest.TestCase):
    def setUp(self):
        self.fa = dt.datetime(2026, 1, 1, 0, 0, 0)

    def test_filters_invalid_timestamps(self):
        pts = [
            {"t": 0, "p": "0.5"},
            {"t": -1, "p": 0.6},
            {"t": "1736035200", "p": 0.7},  # 2026-01-05
        ]
        rows = prices_history_to_rows("TID", pts, self.fa, fidelity=60)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "TID")
        self.assertAlmostEqual(rows[0][2], 0.7)
        self.assertEqual(rows[0][3], 60)
        self.assertEqual(rows[0][4], self.fa)

    def test_passes_fidelity(self):
        pts = [{"t": 1735689600, "p": 0.5}]
        rows = prices_history_to_rows("TID", pts, self.fa, fidelity=1440)
        self.assertEqual(rows[0][3], 1440)

    def test_empty_points_yields_no_rows(self):
        self.assertEqual(prices_history_to_rows("TID", [], self.fa, 60), [])


class BookToRowsTests(unittest.TestCase):
    def setUp(self):
        self.fa = dt.datetime(2026, 1, 1)

    def test_emits_bid_and_ask_levels(self):
        book = {
            "asset_id": "TID",
            "market": "M1",
            "timestamp": "1735689600",
            "hash": "h1",
            "bids": [{"price": "0.5", "size": "100"}],
            "asks": [{"price": "0.6", "size": "50"}, {"price": "0.7", "size": "10"}],
        }
        rows = book_to_rows(book, self.fa)
        self.assertEqual(len(rows), 3)
        sides = [r[2] for r in rows]
        self.assertEqual(sides.count("bid"), 1)
        self.assertEqual(sides.count("ask"), 2)
        # column order: token_id, market, side, price, size, ts, hash, fa
        bid = [r for r in rows if r[2] == "bid"][0]
        self.assertEqual(bid[0], "TID")
        self.assertEqual(bid[1], "M1")
        self.assertAlmostEqual(bid[3], 0.5)
        self.assertAlmostEqual(bid[4], 100.0)
        self.assertEqual(bid[6], "h1")
        self.assertEqual(bid[7], self.fa)

    def test_falls_back_to_token_id_when_asset_id_absent(self):
        book = {"token_id": "TID2", "market": "", "bids": [], "asks": []}
        rows = book_to_rows(book, self.fa)
        self.assertEqual(rows, [])

    def test_empty_book_returns_empty(self):
        self.assertEqual(book_to_rows({}, self.fa), [])
        self.assertEqual(book_to_rows(None, self.fa), [])


class QuotesToRowsTests(unittest.TestCase):
    def setUp(self):
        self.fa = dt.datetime(2026, 1, 1)

    def test_buy_becomes_best_bid_sell_becomes_best_ask(self):
        per_token = {
            "TID": {
                "midpoint": 0.5,
                "spread": 0.02,
                "best_buy": 0.51,
                "best_sell": 0.49,
                "last_trade_price": 0.5,
                "last_trade_side": "BUY",
            },
        }
        rows = quotes_to_rows(per_token, self.fa)
        self.assertEqual(len(rows), 1)
        # column order: tid, mid, bid, ask, spread, ltp, lt_side, fa
        self.assertEqual(rows[0][0], "TID")
        self.assertAlmostEqual(rows[0][1], 0.5)
        self.assertAlmostEqual(rows[0][2], 0.51)  # best_bid = best_buy
        self.assertAlmostEqual(rows[0][3], 0.49)  # best_ask = best_sell
        self.assertAlmostEqual(rows[0][4], 0.02)
        self.assertEqual(rows[0][6], "BUY")
        self.assertEqual(rows[0][7], self.fa)

    def test_empty_dict_yields_no_rows(self):
        self.assertEqual(quotes_to_rows({}, self.fa), [])


if __name__ == "__main__":
    unittest.main()
