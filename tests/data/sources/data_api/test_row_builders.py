"""Unit tests for data_api row-builder functions."""
from __future__ import annotations

import datetime as dt
import unittest

from data.sources.data_api.puller import trade_to_row, holder_to_row, oi_to_row


# Insert column order for dataapi_trades, mirrored from puller.insert_trades.
DATAAPI_TRADES_COLUMNS = [
    "condition_id", "tx_hash", "trade_time", "proxy_wallet", "side", "asset",
    "size", "price", "outcome", "outcome_index", "title", "slug", "event_slug",
    "icon", "display_name", "pseudonym", "bio", "profile_image",
    "profile_image_optimized", "fetched_at",
]

DATAAPI_HOLDERS_COLUMNS = [
    "condition_id", "asset", "outcome_index", "proxy_wallet", "amount",
    "display_name", "pseudonym", "bio", "profile_image",
    "profile_image_optimized", "verified", "display_username_public",
    "fetched_at",
]


class TradeToRowTests(unittest.TestCase):
    def setUp(self):
        self.fa = dt.datetime(2026, 1, 1)

    def test_lowercases_proxy_wallet(self):
        t = {"proxyWallet": "0xABCDEF"}
        row = trade_to_row(t, self.fa)
        idx = DATAAPI_TRADES_COLUMNS.index("proxy_wallet")
        self.assertEqual(row[idx], "0xabcdef")

    def test_zero_timestamp_yields_epoch(self):
        t = {"timestamp": 0}
        row = trade_to_row(t, self.fa)
        self.assertEqual(row[DATAAPI_TRADES_COLUMNS.index("trade_time")],
                         dt.datetime(1970, 1, 1))

    def test_valid_timestamp(self):
        # 2025-01-05 00:00:00 UTC
        t = {"timestamp": 1736035200}
        row = trade_to_row(t, self.fa)
        self.assertEqual(row[DATAAPI_TRADES_COLUMNS.index("trade_time")],
                         dt.datetime(2025, 1, 5))

    def test_column_count_matches_insert_sql(self):
        row = trade_to_row({}, self.fa)
        self.assertEqual(len(row), len(DATAAPI_TRADES_COLUMNS))
        # fetched_at is at the end
        self.assertEqual(row[-1], self.fa)


class HolderToRowTests(unittest.TestCase):
    def setUp(self):
        self.fa = dt.datetime(2026, 1, 1)

    def test_uses_token_fallback_when_asset_missing(self):
        h = {"_token": "TID_FALLBACK", "proxyWallet": "0xABC"}
        row = holder_to_row(h, "0xCID", self.fa)
        idx = DATAAPI_HOLDERS_COLUMNS.index("asset")
        self.assertEqual(row[idx], "TID_FALLBACK")

    def test_prefers_asset_over_token(self):
        h = {"asset": "real", "_token": "fallback"}
        row = holder_to_row(h, "0xCID", self.fa)
        self.assertEqual(row[DATAAPI_HOLDERS_COLUMNS.index("asset")], "real")

    def test_lowercases_proxy_wallet(self):
        row = holder_to_row({"proxyWallet": "0xUPPER"}, "cid", self.fa)
        self.assertEqual(row[DATAAPI_HOLDERS_COLUMNS.index("proxy_wallet")],
                         "0xupper")

    def test_column_count_matches_insert_sql(self):
        row = holder_to_row({}, "cid", self.fa)
        self.assertEqual(len(row), len(DATAAPI_HOLDERS_COLUMNS))
        self.assertEqual(row[0], "cid")
        self.assertEqual(row[-1], self.fa)

    def test_bool_fields_coerced_to_uint8(self):
        h = {"verified": True, "displayUsernamePublic": False}
        row = holder_to_row(h, "cid", self.fa)
        self.assertEqual(row[DATAAPI_HOLDERS_COLUMNS.index("verified")], 1)
        self.assertEqual(
            row[DATAAPI_HOLDERS_COLUMNS.index("display_username_public")], 0,
        )


class OiToRowTests(unittest.TestCase):
    def test_minimal(self):
        fa = dt.datetime(2026, 1, 1)
        row = oi_to_row({"market": "M1", "value": "1234.5"}, fa)
        self.assertEqual(row, ("M1", 1234.5, fa))

    def test_missing_value_zero(self):
        fa = dt.datetime(2026, 1, 1)
        row = oi_to_row({"market": "M1"}, fa)
        self.assertEqual(row, ("M1", 0.0, fa))


if __name__ == "__main__":
    unittest.main()
