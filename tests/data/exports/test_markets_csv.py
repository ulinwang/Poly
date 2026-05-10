"""Smoke tests for data.exports.markets_csv.main — patches the bare
clickhouse_driver.Client and checks header + serialization."""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from data.exports import markets_csv


def _fake_client_factory(rows):
    fake = mock.MagicMock()
    fake.execute.return_value = [(len(rows),)]
    fake.execute_iter.return_value = iter(rows)
    return mock.MagicMock(return_value=fake)


class MarketsCsvTests(unittest.TestCase):
    def test_writes_header_and_array_columns_as_json(self):
        # Build one row matching markets_csv.COLUMNS field order.
        # market_id, slug, question, description, category,
        # outcomes, clob_token_ids, outcome_prices,
        # volume, end_date, active, closed, fetched_at
        sample = (
            "M1", "slug-1", "Q?", "desc", "cat",
            ["Yes", "No"], ["T1", "T2"], [0.5, 0.5],
            12345.0, "2026-01-01", 1, 0, "2026-05-09",
        )
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "x.csv"
            client_class = _fake_client_factory([sample])
            with mock.patch.object(markets_csv, "Client", client_class), \
                 mock.patch.object(sys, "argv", ["markets_csv", "--out", str(out)]):
                markets_csv.main()
            with out.open() as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[0], markets_csv.COLUMNS)
            # Array columns should be JSON-serialized.
            outcomes_idx = markets_csv.COLUMNS.index("outcomes")
            self.assertEqual(json.loads(rows[1][outcomes_idx]), ["Yes", "No"])
            prices_idx = markets_csv.COLUMNS.index("outcome_prices")
            self.assertEqual(json.loads(rows[1][prices_idx]), [0.5, 0.5])

    def test_array_value_lossless_roundtrip(self):
        sample = (
            "M1", "s", "Q", "d", "c",
            ["one"], [], [],
            0.0, None, 0, 0, None,
        )
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "y.csv"
            client_class = _fake_client_factory([sample])
            with mock.patch.object(markets_csv, "Client", client_class), \
                 mock.patch.object(sys, "argv", ["markets_csv", "--out", str(out)]):
                markets_csv.main()
            with out.open() as f:
                rows = list(csv.reader(f))
            outcomes_idx = markets_csv.COLUMNS.index("outcomes")
            self.assertEqual(json.loads(rows[1][outcomes_idx]), ["one"])
            # None values become empty strings in CSV.
            end_date_idx = markets_csv.COLUMNS.index("end_date")
            self.assertEqual(rows[1][end_date_idx], "")

    def test_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as t:
            nested = Path(t) / "a" / "b" / "c.csv"
            client_class = _fake_client_factory([])
            with mock.patch.object(markets_csv, "Client", client_class), \
                 mock.patch.object(sys, "argv",
                                    ["markets_csv", "--out", str(nested)]):
                markets_csv.main()
            self.assertTrue(nested.exists())


if __name__ == "__main__":
    unittest.main()
