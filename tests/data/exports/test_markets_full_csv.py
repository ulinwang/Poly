"""Smoke tests for data.exports.markets_full_csv.main."""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from data.exports import markets_full_csv
from data.sources.gamma_api.puller import FIELDS, EXTRA_COLS


ALL_COLUMNS = ([name for name, *_ in FIELDS]
               + [name for name, _ in EXTRA_COLS])


def _fake_client_factory(rows):
    fake = mock.MagicMock()
    fake.execute.return_value = [(len(rows),)]
    fake.execute_iter.return_value = iter(rows)
    return mock.MagicMock(return_value=fake)


def _empty_row(columns):
    """Build a row with sane defaults for each column based on its name."""
    out = []
    for col in columns:
        if col in markets_full_csv.ARRAY_COLS:
            out.append([])
        elif col == "outcomes":
            out.append([])
        else:
            out.append("")
    return tuple(out)


class MarketsFullCsvTests(unittest.TestCase):
    def test_default_writes_all_columns_in_header(self):
        row = _empty_row(ALL_COLUMNS)
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "f.csv"
            with mock.patch.object(markets_full_csv, "Client",
                                    _fake_client_factory([row])), \
                 mock.patch.object(sys, "argv",
                                    ["markets_full_csv", "--out", str(out)]):
                markets_full_csv.main()
            with out.open() as f:
                header = next(csv.reader(f))
            self.assertEqual(header, ALL_COLUMNS)

    def test_no_raw_drops_raw_json_column(self):
        cols = [c for c in ALL_COLUMNS if c != "raw_json"]
        row = _empty_row(cols)
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "f.csv"
            with mock.patch.object(markets_full_csv, "Client",
                                    _fake_client_factory([row])), \
                 mock.patch.object(sys, "argv",
                                    ["markets_full_csv", "--out", str(out),
                                     "--no-raw"]):
                markets_full_csv.main()
            with out.open() as f:
                header = next(csv.reader(f))
            self.assertNotIn("raw_json", header)
            self.assertEqual(header, cols)

    def test_array_columns_serialized_as_json(self):
        # Build a row where outcomes = ["Yes","No"], rest empty
        row_vals = []
        for col in ALL_COLUMNS:
            if col == "outcomes":
                row_vals.append(["Yes", "No"])
            elif col == "outcome_prices":
                row_vals.append([0.55, 0.45])
            elif col in markets_full_csv.ARRAY_COLS:
                row_vals.append([])
            else:
                row_vals.append("")
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "f.csv"
            with mock.patch.object(markets_full_csv, "Client",
                                    _fake_client_factory([tuple(row_vals)])), \
                 mock.patch.object(sys, "argv",
                                    ["markets_full_csv", "--out", str(out)]):
                markets_full_csv.main()
            with out.open() as f:
                rows = list(csv.reader(f))
            outcomes_idx = ALL_COLUMNS.index("outcomes")
            self.assertEqual(json.loads(rows[1][outcomes_idx]), ["Yes", "No"])
            prices_idx = ALL_COLUMNS.index("outcome_prices")
            self.assertEqual(json.loads(rows[1][prices_idx]), [0.55, 0.45])


if __name__ == "__main__":
    unittest.main()
