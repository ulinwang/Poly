"""Unit tests for experiments.analysis.pnl — pure aggregation."""
from __future__ import annotations

import unittest

from experiments.analysis.pnl import aggregate_by_persona, total_traded_volume


class AggregateByPersonaTests(unittest.TestCase):
    def test_groups_and_computes_basic_stats(self):
        pnl = {1: 10.0, 2: 20.0, 3: -5.0, 4: 100.0}
        persona_of = {1: "whale", 2: "whale", 3: "minnow", 4: "minnow"}
        out = aggregate_by_persona(pnl, persona_of)
        self.assertEqual(set(out.keys()), {"whale", "minnow"})
        self.assertEqual(out["whale"]["n"], 2)
        self.assertAlmostEqual(out["whale"]["mean"], 15.0)
        self.assertAlmostEqual(out["whale"]["min"], 10.0)
        self.assertAlmostEqual(out["whale"]["max"], 20.0)
        self.assertEqual(out["minnow"]["n"], 2)
        self.assertAlmostEqual(out["minnow"]["min"], -5.0)

    def test_unknown_persona_label_for_unmapped_agent(self):
        pnl = {1: 10.0, 99: 5.0}
        persona_of = {1: "named"}
        out = aggregate_by_persona(pnl, persona_of)
        self.assertIn("Unknown", out)
        self.assertEqual(out["Unknown"]["n"], 1)
        self.assertAlmostEqual(out["Unknown"]["mean"], 5.0)

    def test_empty_pnl_returns_empty(self):
        self.assertEqual(aggregate_by_persona({}, {}), {})

    def test_median_uses_middle_index(self):
        pnl = {1: 1.0, 2: 5.0, 3: 100.0}
        persona_of = {1: "p", 2: "p", 3: "p"}
        out = aggregate_by_persona(pnl, persona_of)
        # sorted: [1, 5, 100] → n//2 = 1 → 5
        self.assertAlmostEqual(out["p"]["median"], 5.0)


class TotalTradedVolumeTests(unittest.TestCase):
    def test_default_indices_match_fills_log_shape(self):
        # Layout: (sim_id, tick, maker_oid, taker_oid, maker_aid, taker_aid,
        #          outcome, maker_side, price, size, notional, ts)
        fills = [
            ("s", 0, 0, 0, 0, 0, "YES", "BUY", 0.5, 10.0, 5.0, 0),
            ("s", 1, 0, 0, 0, 0, "NO", "SELL", 0.4, 5.0, 2.0, 0),
        ]
        # 0.5*10 + 0.4*5 = 5 + 2 = 7
        self.assertAlmostEqual(total_traded_volume(fills), 7.0)

    def test_custom_indices(self):
        fills = [(0.6, 5.0), (0.2, 10.0)]
        self.assertAlmostEqual(
            total_traded_volume(fills, fill_price_idx=0, fill_size_idx=1),
            0.6 * 5.0 + 0.2 * 10.0,
        )

    def test_empty_returns_zero(self):
        self.assertEqual(total_traded_volume([]), 0.0)

    def test_string_numbers_coerced_to_float(self):
        fills = [(None, None, None, None, None, None, None, None, "0.5", "8")]
        self.assertAlmostEqual(total_traded_volume(fills), 4.0)


if __name__ == "__main__":
    unittest.main()
