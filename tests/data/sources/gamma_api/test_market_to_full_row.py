"""Unit tests for data.sources.gamma_api.puller.market_to_full_row."""
from __future__ import annotations

import datetime as dt
import json
import unittest

from data.sources.gamma_api.puller import (
    market_to_full_row, FIELDS, EXTRA_COLS,
)


COLUMN_NAMES = [name for name, *_ in FIELDS] + [name for name, _ in EXTRA_COLS]


class MarketToFullRowTests(unittest.TestCase):
    def test_row_length_matches_fields_plus_extras(self):
        fa = dt.datetime(2026, 1, 1)
        row = market_to_full_row({}, fa)
        self.assertEqual(len(row), len(COLUMN_NAMES))

    def test_uses_provided_fetched_at(self):
        fa = dt.datetime(2026, 5, 9)
        row = market_to_full_row({"id": "M1"}, fa)
        # last column is fetched_at
        self.assertEqual(row[-1], fa)

    def test_handles_missing_keys_with_defaults(self):
        fa = dt.datetime(2026, 1, 1)
        row = market_to_full_row({}, fa)
        idx = COLUMN_NAMES.index
        self.assertEqual(row[idx("market_id")], "")
        self.assertEqual(row[idx("active")], 0)
        self.assertEqual(row[idx("liquidity")], 0.0)
        self.assertEqual(row[idx("outcomes")], [])
        # raw_json contains the full original payload
        self.assertEqual(row[idx("raw_json")], "{}")

    def test_json_array_string_decoded_to_array(self):
        fa = dt.datetime(2026, 1, 1)
        m = {
            "id": "X",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.55","0.45"]',
        }
        row = market_to_full_row(m, fa)
        idx = COLUMN_NAMES.index
        self.assertEqual(row[idx("outcomes")], ["Yes", "No"])
        self.assertEqual(row[idx("outcome_prices")], [0.55, 0.45])

    def test_raw_json_preserves_all_input_keys(self):
        fa = dt.datetime(2026, 1, 1)
        m = {"id": "X", "extra_field_we_dont_track": 42}
        row = market_to_full_row(m, fa)
        raw = json.loads(row[COLUMN_NAMES.index("raw_json")])
        self.assertEqual(raw["extra_field_we_dont_track"], 42)

    def test_default_fetched_at_when_none(self):
        # Passing None uses utcnow() — verify it returned a recent datetime
        before = dt.datetime.utcnow()
        row = market_to_full_row({}, None)
        after = dt.datetime.utcnow()
        ts = row[-1]
        self.assertGreaterEqual(ts, before)
        self.assertLessEqual(ts, after)


if __name__ == "__main__":
    unittest.main()
