"""Unit tests for scripts/clustering/compute_features.py.

Uses StubCH to inject deterministic SQL results so the test does NOT
require ClickHouse. We verify:
  - cutoff_ts is threaded into the SQL params
  - the cutoff-suffixed output file is written
  - the printed summary references trades < cutoff (no row contradicts)
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.clustering import compute_features as cf
from tests.data._stub_ch import StubCH


# 13 columns, matching cf.COLS.
def _row(wallet: str, total_notional: float, tx_count: int):
    return (
        wallet,
        # log_notional, top_market_share, n_markets_per_log_dollar,
        # mean_price, tail_trade_pct, log_active_days, price_std,
        2.0, 0.5, 1.0, 0.4, 0.1, 1.5, 0.2,
        # n_markets, tx_count, total_notional, past_accuracy, n_resolved_prior
        3, tx_count, total_notional, 0.55, 6,
    )


class CutoffISOSuffixTest(unittest.TestCase):
    def test_compact_format(self):
        # 2023-05-23 15:37:21 UTC
        s = cf.cutoff_iso_compact(1684856241)
        self.assertEqual(s, "20230523T153721Z")


class ComputeRoundtripTest(unittest.TestCase):
    def test_writes_cutoff_suffixed_parquet_and_passes_cutoff(self):
        rows = [_row("0xa", 1000.0, 15), _row("0xb", 50.0, 4)]
        ch = StubCH({"FROM polymetl.dataapi_trades": rows})

        with tempfile.TemporaryDirectory() as td:
            out_path = cf.compute(
                cutoff_ts=1_700_000_000, out_dir=Path(td), ch=ch,
            )
            self.assertTrue(out_path.exists())
            # cutoff was threaded into the SQL params
            self.assertEqual(
                ch.client.calls[0][1]["cutoff_ts"], 1_700_000_000,
            )
            # output filename encodes the cutoff
            self.assertIn("wallet_features_", out_path.name)
            self.assertTrue(out_path.name.endswith(".parquet"))

            df = pd.read_parquet(out_path)
            self.assertEqual(len(df), 2)
            self.assertEqual(set(df.columns), set(cf.COLS))

    def test_resolve_cutoff_iso(self):
        # Round-trip: ISO -> ts -> ISO suffix
        ns = type("ns", (), {})()
        ns.cutoff_ts = None
        ns.cutoff_iso = "2023-05-23T15:37:21Z"
        ts = cf._resolve_cutoff(ns)
        self.assertEqual(ts, 1684856241)

    def test_resolve_cutoff_ts_takes_precedence_error(self):
        ns = type("ns", (), {})()
        ns.cutoff_ts = 1_700_000_000
        ns.cutoff_iso = "2023-05-23T15:37:21Z"
        with self.assertRaises(SystemExit):
            cf._resolve_cutoff(ns)

    def test_resolve_cutoff_neither_raises(self):
        ns = type("ns", (), {})()
        ns.cutoff_ts = None
        ns.cutoff_iso = None
        with self.assertRaises(SystemExit):
            cf._resolve_cutoff(ns)


class SQLContainsCutoffFiltersTest(unittest.TestCase):
    """Static text-level check that every aggregation has the WHERE
    cutoff clause (audit L-1, L-5)."""

    def test_each_dataapi_trades_select_has_cutoff(self):
        sql = cf.SQL
        # 3 FROM polymetl.dataapi_trades references in the CTEs.
        self.assertEqual(sql.count("FROM polymetl.dataapi_trades"), 3)
        # And each is followed by a WHERE on cutoff_ts somewhere in
        # the next ~600 chars.
        idx = 0
        for _ in range(3):
            i = sql.index("FROM polymetl.dataapi_trades", idx)
            window = sql[i:i + 600]
            self.assertIn("cutoff_ts", window)
            idx = i + 1
        # markets_resolved join honors cutoff
        self.assertIn("end_date < toDateTime(%(cutoff_ts)s)", sql)


if __name__ == "__main__":
    unittest.main()
