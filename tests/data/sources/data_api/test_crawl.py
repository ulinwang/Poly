"""Crawl/orchestration tests for data_api.puller — StubCH + mocks."""
from __future__ import annotations

import unittest
from unittest import mock

from data.sources.data_api import puller as dapi
from tests.data._stub_ch import StubCH


class CrawlEndpointTests(unittest.TestCase):
    def setUp(self):
        # Capture all SQL passing through the StubClient.
        self.executed: list[str] = []
        self.ch = StubCH({})

        def execute(sql, params=None):
            self.executed.append(sql)
            return []
        self.ch.client.execute = execute  # type: ignore

    def test_dispatches_trades_endpoint(self):
        with mock.patch.object(dapi, "fetch_trades",
                               return_value=[{"transactionHash": "h1"}]):
            stats = dapi.crawl_endpoint(
                self.ch, "trades", ["0xCID"], workers=1, batch=10,
            )
        self.assertEqual(stats["markets_done"], 1)
        self.assertEqual(stats["rows_inserted"], 1)
        self.assertEqual(stats["errors"], 0)
        # Insert + mark_progress should both have run.
        joined = "\n".join(self.executed)
        self.assertIn("INSERT INTO polymetl.dataapi_trades", joined)
        self.assertIn("INSERT INTO polymetl.dataapi_progress", joined)

    def test_dispatches_holders_endpoint(self):
        with mock.patch.object(dapi, "fetch_holders",
                               return_value=[{"proxyWallet": "W"}]):
            stats = dapi.crawl_endpoint(
                self.ch, "holders", ["0xCID"], workers=1, batch=10,
            )
        self.assertEqual(stats["markets_done"], 1)
        self.assertIn("INSERT INTO polymetl.dataapi_holders",
                      "\n".join(self.executed))

    def test_unknown_endpoint_raises(self):
        with self.assertRaises(ValueError):
            dapi.crawl_endpoint(self.ch, "garbage", ["x"])

    def test_fetcher_exception_counts_error_no_progress(self):
        with mock.patch.object(dapi, "fetch_trades",
                               side_effect=RuntimeError("boom")):
            stats = dapi.crawl_endpoint(
                self.ch, "trades", ["0xCID"], workers=1, batch=10,
            )
        self.assertEqual(stats["markets_done"], 0)
        self.assertEqual(stats["errors"], 1)
        self.assertNotIn("INSERT INTO polymetl.dataapi_progress",
                         "\n".join(self.executed))


class ListConditionIdsTests(unittest.TestCase):
    def test_orders_by_volume_when_default(self):
        captured = {}
        def execute(sql, params=None):
            captured["sql"] = sql
            return [("CID1",), ("CID2",)]
        ch = StubCH({})
        ch.client.execute = execute  # type: ignore
        out = dapi.list_condition_ids(ch)
        self.assertEqual(out, ["CID1", "CID2"])
        self.assertIn("ORDER BY volume DESC", captured["sql"])

    def test_orders_by_market_id_when_disabled(self):
        captured = {}
        def execute(sql, params=None):
            captured["sql"] = sql
            return []
        ch = StubCH({})
        ch.client.execute = execute  # type: ignore
        dapi.list_condition_ids(ch, order_by_volume=False)
        self.assertIn("ORDER BY market_id", captured["sql"])

    def test_limit_appended_when_set(self):
        captured = {}
        def execute(sql, params=None):
            captured["sql"] = sql
            return []
        ch = StubCH({})
        ch.client.execute = execute  # type: ignore
        dapi.list_condition_ids(ch, limit=5)
        self.assertIn("LIMIT 5", captured["sql"])

    def test_skips_blank_condition_ids(self):
        ch = StubCH({})
        ch.client.execute = lambda sql, params=None: [("CID1",), ("",)]  # type: ignore
        self.assertEqual(dapi.list_condition_ids(ch), ["CID1"])


class AlreadyDoneTests(unittest.TestCase):
    def test_returns_set_for_endpoint(self):
        ch = StubCH({"FROM polymetl.dataapi_progress": [("C1",), ("C2",), ("C1",)]})
        out = dapi.already_done(ch, "trades")
        self.assertEqual(out, {"C1", "C2"})


if __name__ == "__main__":
    unittest.main()
