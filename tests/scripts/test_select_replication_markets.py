"""Tests for the multi-market sampler (D1)."""
from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.select_replication_markets import (
    _balance_pick, _volume_decile, select_markets, validate_selection,
)


def _candidate(slug: str, wi: int, volume: float) -> dict:
    return {
        "slug": slug,
        "condition_id": f"0x{slug}",
        "winning_idx": wi,
        "volume": volume,
        "end_date": "2024-01-01T00:00:00",
        "question": f"Q {slug}",
        "n_wallets": 100,
    }


class VolumeDecileTest(unittest.TestCase):
    def test_decile_distribution(self):
        vols = [float(i) for i in range(1, 101)]
        # smallest -> decile 0; largest -> decile 9
        self.assertEqual(_volume_decile(vols, 1.0), 0)
        self.assertEqual(_volume_decile(vols, 100.0), 9)
        # midpoint roughly in 4..5
        d = _volume_decile(vols, 50.0)
        self.assertIn(d, (4, 5))


class BalancePickTest(unittest.TestCase):
    def test_balance_within_tolerance_yes_no(self):
        import random
        rng = random.Random(0)
        cands = []
        # 10 YES across 10 deciles, 10 NO across 10 deciles
        for i in range(10):
            cands.append(_candidate(f"yes{i}", 1, 10 ** (i / 2 + 1)))
            cands.append(_candidate(f"no{i}", 0, 10 ** (i / 2 + 1)))
        picks = _balance_pick(cands, n=10, rng=rng, balance="yes_no")
        self.assertEqual(len(picks), 10)
        yes = sum(1 for p in picks if p["winning_idx"] == 1)
        no = sum(1 for p in picks if p["winning_idx"] == 0)
        self.assertLessEqual(abs(yes - no), 1,
                             f"yes={yes} no={no}")

    def test_volume_decile_spread(self):
        import random
        rng = random.Random(0)
        cands = []
        for i in range(20):
            cands.append(_candidate(f"yes{i}", 1, 10 ** (i / 3 + 1)))
            cands.append(_candidate(f"no{i}", 0, 10 ** (i / 3 + 1)))
        picks = _balance_pick(cands, n=10, rng=rng, balance="yes_no")
        vols = [p["volume"] for p in picks]
        deciles = {_volume_decile(vols, v) for v in vols}
        self.assertGreaterEqual(len(deciles), 4,
                                f"only {len(deciles)} deciles hit")

    def test_determinism_given_seed(self):
        import random
        cands = [_candidate(f"y{i}", 1, 10.0 ** (i / 2 + 1))
                 for i in range(15)]
        cands += [_candidate(f"n{i}", 0, 10.0 ** (i / 2 + 1))
                  for i in range(15)]
        r1 = _balance_pick(cands, n=10, rng=random.Random(42),
                           balance="yes_no")
        r2 = _balance_pick(cands, n=10, rng=random.Random(42),
                           balance="yes_no")
        self.assertEqual([p["slug"] for p in r1], [p["slug"] for p in r2])


class SelectMarketsTest(unittest.TestCase):
    def test_select_with_injected_fns(self):
        # Mock select_fn (returns rows) and meta_fn (returns winning_idx)
        rows = []
        end = dt.datetime(2024, 1, 1)
        for i in range(8):
            rows.append(
                (f"slug-yes-{i}", f"0xy{i}", 10.0 ** (i + 2), 100, end,
                 f"Q yes {i}")
            )
            rows.append(
                (f"slug-no-{i}", f"0xn{i}", 10.0 ** (i + 2), 100, end,
                 f"Q no {i}")
            )

        def select_fn(**kwargs):
            return rows

        def meta_fn(slug, ch=None):
            return {"winning_idx": 1 if "yes" in slug else 0}

        out = select_markets(
            n=6, min_volume=0, max_volume=1e12, min_wallets=0,
            balance="yes_no", seed=0,
            select_fn=select_fn, meta_fn=meta_fn,
        )
        self.assertEqual(len(out), 6)
        yes = sum(1 for o in out if o["winning_idx"] == 1)
        no = sum(1 for o in out if o["winning_idx"] == 0)
        self.assertLessEqual(abs(yes - no), 1)


class ValidateModeTest(unittest.TestCase):
    def test_validation_reports_problems(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.yaml"
            p.write_text(yaml.safe_dump({
                "markets": [
                    {"slug": "a", "winning_idx": 1, "volume": 100.0},
                    {"slug": "a", "winning_idx": 1, "volume": 200.0},  # dup
                    {"slug": "c", "winning_idx": 1, "volume": 300.0},
                ],
            }))
            ok, report = validate_selection(p)
            self.assertFalse(ok)
            # both imbalance (3 YES vs 0 NO) and dup-slug should fire
            self.assertTrue(any("imbalance" in s for s in report["problems"]))
            self.assertTrue(any("duplicate" in s for s in report["problems"]))

    def test_validation_passes_balanced(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "good.yaml"
            p.write_text(yaml.safe_dump({
                "markets": [
                    {"slug": "a", "winning_idx": 1, "volume": 100.0},
                    {"slug": "b", "winning_idx": 0, "volume": 500.0},
                    {"slug": "c", "winning_idx": 1, "volume": 2000.0},
                    {"slug": "d", "winning_idx": 0, "volume": 10000.0},
                ],
            }))
            ok, report = validate_selection(p)
            self.assertEqual(report["yes_resolved"], 2)
            self.assertEqual(report["no_resolved"], 2)


if __name__ == "__main__":
    unittest.main()
