from __future__ import annotations

import datetime as dt
import json
import unittest

from data.query import markets as q
from tests.data._stub_ch import StubCH


def _meta_route(_):
    return [(
        "0xCID", "spacex", "Will it work?",
        json.dumps([
            {"token_id": "TYES", "outcome": "Yes"},
            {"token_id": "TNO", "outcome": "No"},
        ]),
        0.001, 0.0,
        dt.datetime(2025, 10, 14), dt.datetime(2025, 9, 10),
        1, dt.datetime(2025, 10, 14), ["Yes", "No"],
        "the desc", 36376.0,
    )]


class GetMarketMetaTest(unittest.TestCase):
    def test_returns_full_dict(self):
        ch = StubCH({"FROM polymetl.clob_markets": _meta_route})
        meta = q.get_market_meta("spacex", ch=ch)
        self.assertEqual(meta["yes_token_id"], "TYES")
        self.assertEqual(meta["no_token_id"], "TNO")
        self.assertEqual(meta["winning_idx"], 1)
        self.assertEqual(meta["tick_size"], 0.001)
        self.assertEqual(meta["question"], "Will it work?")
        self.assertEqual(meta["description"], "the desc")

    def test_unknown_slug_returns_none(self):
        ch = StubCH({"FROM polymetl.clob_markets": []})
        self.assertIsNone(q.get_market_meta("nope", ch=ch))


class SelectResolvedMarketsTest(unittest.TestCase):
    def test_returns_rows(self):
        ch = StubCH({
            "FROM polymetl.markets_resolved": [
                ("foo", "0xA", 10000.0, 50, dt.datetime(2025, 10, 1), "?"),
            ],
        })
        rows = q.select_resolved_markets(min_wallets=10, ch=ch)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "foo")


if __name__ == "__main__":
    unittest.main()
