"""Crawl/orchestration tests for clob_api.puller — StubCH + http mocks."""
from __future__ import annotations

import unittest
from unittest import mock

from data.sources.clob_api import puller as clob
from tests.data._stub_ch import StubCH
from tests._http_mock import (
    fake_urlopen_sequence, fake_urlopen_returning, http_error,
)


class CrawlMarketsTests(unittest.TestCase):
    def setUp(self):
        self.inserts: list[list] = []
        self.ch = StubCH({
            "INSERT INTO polymetl.clob_markets": [],
        })
        # capture rows passed to insert via execute()
        original = self.ch.client.execute
        def capture(sql, params=None):
            if "INSERT INTO polymetl.clob_markets" in sql and isinstance(params, list):
                self.inserts.append(params)
                return []
            return original(sql, params)
        self.ch.client.execute = capture  # type: ignore

    def test_paginates_until_no_next_cursor(self):
        seq = fake_urlopen_sequence([
            {"data": [{"condition_id": "A"}, {"condition_id": "B"}],
             "next_cursor": "abc"},
            {"data": [{"condition_id": "C"}], "next_cursor": "LTE="},
        ])
        with mock.patch.object(clob.urllib.request, "urlopen", seq):
            total = clob.crawl_markets(self.ch)
        self.assertEqual(total, 3)
        self.assertEqual(len(self.inserts), 2)

    def test_breaks_on_empty_data(self):
        seq = fake_urlopen_sequence([{"data": [], "next_cursor": "x"}])
        with mock.patch.object(clob.urllib.request, "urlopen", seq):
            self.assertEqual(clob.crawl_markets(self.ch), 0)
        self.assertEqual(self.inserts, [])


class FetchPricesHistoryTests(unittest.TestCase):
    def test_falls_back_to_daily_when_hourly_empty(self):
        seq = fake_urlopen_sequence([
            {"history": []},                            # hourly fails
            {"history": [{"t": 1735689600, "p": 0.5}]},  # daily ok
        ])
        with mock.patch.object(clob.urllib.request, "urlopen", seq), \
             mock.patch.object(clob.time, "sleep", lambda *_: None):
            pts, fid = clob.fetch_prices_history("TID")
        self.assertEqual(len(pts), 1)
        self.assertEqual(fid, clob.PRICES_HISTORY_FIDELITY_FALLBACK)

    def test_uses_hourly_when_present(self):
        seq = fake_urlopen_sequence([
            {"history": [{"t": 1735689600, "p": 0.5}]},
        ])
        with mock.patch.object(clob.urllib.request, "urlopen", seq):
            pts, fid = clob.fetch_prices_history("TID")
        self.assertEqual(len(pts), 1)
        self.assertEqual(fid, clob.PRICES_HISTORY_FIDELITY_PRIMARY)


class FetchBookTests(unittest.TestCase):
    def test_returns_none_on_404(self):
        seq = fake_urlopen_sequence([http_error(404)])
        with mock.patch.object(clob.urllib.request, "urlopen", seq):
            self.assertIsNone(clob.fetch_book("TID"))

    def test_returns_book_dict_on_success(self):
        with mock.patch.object(clob.urllib.request, "urlopen",
                                fake_urlopen_returning({"asset_id": "TID"})):
            self.assertEqual(clob.fetch_book("TID"), {"asset_id": "TID"})


class FetchQuotesBatchTests(unittest.TestCase):
    def test_assembles_per_token_dict(self):
        # POST sequence: midpoints, spreads, prices, last-trades-prices
        seq = fake_urlopen_sequence([
            {"T1": "0.5"},                                          # midpoints
            {"T1": "0.02"},                                         # spreads
            {"T1": {"BUY": "0.51", "SELL": "0.49"}},                # prices
            [{"token_id": "T1", "price": "0.5", "side": "BUY"}],     # last-trades
        ])
        with mock.patch.object(clob.urllib.request, "urlopen", seq):
            out = clob.fetch_quotes_batch(["T1"])
        self.assertIn("T1", out)
        self.assertAlmostEqual(out["T1"]["midpoint"], 0.5)
        self.assertAlmostEqual(out["T1"]["spread"], 0.02)
        self.assertAlmostEqual(out["T1"]["best_buy"], 0.51)
        self.assertAlmostEqual(out["T1"]["best_sell"], 0.49)
        self.assertAlmostEqual(out["T1"]["last_trade_price"], 0.5)
        self.assertEqual(out["T1"]["last_trade_side"], "BUY")


class ProgressTests(unittest.TestCase):
    def test_already_done_returns_set(self):
        ch = StubCH({"FROM polymetl.clob_progress": [("T1",), ("T2",), ("T1",)]})
        out = clob.already_done(ch, "orderbook")
        self.assertEqual(out, {"T1", "T2"})

    def test_list_token_ids_active_branch(self):
        captured = {}
        def execute(sql, params=None):
            captured["sql"] = sql
            return [("T1",), ("T2",)]
        ch = StubCH({})
        ch.client.execute = execute  # type: ignore
        out = clob.list_token_ids(ch, only_active=True)
        self.assertEqual(out, ["T1", "T2"])
        self.assertIn("accepting_orders = 1", captured["sql"])

    def test_list_token_ids_all_branch(self):
        captured = {}
        def execute(sql, params=None):
            captured["sql"] = sql
            return [("T1",)]
        ch = StubCH({})
        ch.client.execute = execute  # type: ignore
        clob.list_token_ids(ch, only_active=False)
        self.assertNotIn("accepting_orders = 1", captured["sql"])


if __name__ == "__main__":
    unittest.main()
