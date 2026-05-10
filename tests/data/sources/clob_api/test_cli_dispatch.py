"""Smoke tests for clob_api.puller.main argparse dispatch."""
from __future__ import annotations

import sys
import unittest
from unittest import mock

from data.sources.clob_api import puller as clob


class MainDispatchTests(unittest.TestCase):
    def setUp(self):
        # All of these need to be no-ops to keep the test offline.
        self.patches = [
            mock.patch.object(clob, "ensure_clob_schemas"),
            mock.patch.object(clob, "ClickHouse"),
            mock.patch.object(clob, "get_settings"),
            mock.patch.object(clob, "list_token_ids", return_value=["T1", "T2"]),
            mock.patch.object(clob, "already_done", return_value=set()),
            mock.patch.object(clob, "crawl_markets", return_value=0),
            mock.patch.object(clob, "crawl_prices_history",
                              return_value={"tokens_done": 2, "rows": 0, "errors": 0}),
            mock.patch.object(clob, "crawl_orderbook",
                              return_value={"tokens_done": 2, "rows": 0, "errors": 0}),
            mock.patch.object(clob, "crawl_quotes",
                              return_value={"tokens_done": 2, "rows": 0, "errors": 0}),
        ]
        self.mocks = {p.attribute: p.start() for p in self.patches}
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def test_endpoint_markets_invokes_crawl_markets(self):
        with mock.patch.object(sys, "argv",
                                ["clob_api", "--endpoint", "markets"]):
            clob.main()
        self.mocks["crawl_markets"].assert_called_once()

    def test_endpoint_orderbook_skips_already_done(self):
        with mock.patch.object(clob, "already_done", return_value={"T1"}), \
             mock.patch.object(sys, "argv",
                                ["clob_api", "--endpoint", "orderbook"]):
            clob.main()
        # crawl_orderbook should be called with only T2 in todo.
        called_args = self.mocks["crawl_orderbook"].call_args
        self.assertEqual(list(called_args.args[1]), ["T2"])

    def test_invalid_endpoint_exits(self):
        with mock.patch.object(sys, "argv",
                                ["clob_api", "--endpoint", "invalid"]):
            with self.assertRaises(SystemExit):
                clob.main()


if __name__ == "__main__":
    unittest.main()
