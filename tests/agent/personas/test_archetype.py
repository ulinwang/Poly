"""v10 archetype sampling — distribution faithful to source + profile rendering."""
from __future__ import annotations

import json
import os
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd

from agent.personas import archetype as ap
from agent.personas.archetype import (
    build_archetype_population,
    build_archetype_profile_text,
    load_cluster_distribution,
    sample_archetype,
    sample_wallet_in_cluster,
)


HAVE_CLUSTERS = (
    Path("data/clustering/cluster_profiles.json").exists()
    and Path("data/clustering/wallet_clusters.parquet").exists()
)


@unittest.skipUnless(HAVE_CLUSTERS, "cluster artifacts missing — run cluster_wallets.py first")
class ArchetypeSamplingTest(unittest.TestCase):
    def test_load(self):
        d = load_cluster_distribution()
        self.assertIn("K", d)
        self.assertIn("clusters", d)
        self.assertGreater(d["K"], 2)
        probs = sum(d["clusters"][str(c)]["pct"] for c in range(d["K"]))
        self.assertAlmostEqual(probs, 1.0, places=5)

    def test_sample_archetype_distribution(self):
        d = load_cluster_distribution()
        rng = random.Random(42)
        counts = Counter(sample_archetype(rng) for _ in range(10_000))
        # Each empirical bin should be within 2% of expected
        for cid in range(d["K"]):
            expected = d["clusters"][str(cid)]["pct"]
            observed = counts[cid] / 10_000
            self.assertLess(abs(observed - expected), 0.02,
                            f"cluster {cid} drifted: expected {expected:.3f} observed {observed:.3f}")

    def test_sample_wallet_in_cluster(self):
        rng = random.Random(0)
        w = sample_wallet_in_cluster(0, rng)
        self.assertIn("wallet", w)
        self.assertIn("total_notional", w)
        self.assertIn("mean_price", w)

    def test_profile_text_contains_data(self):
        features = {
            "total_notional": 192.50, "tx_count": 18, "n_markets": 12,
            "top_market_share": 0.48, "mean_price": 0.62, "price_std": 0.37,
            "tail_trade_pct": 0.81, "log_active_days": 1.26,  # ~18 days
            "past_accuracy": 0.56, "n_resolved_prior": 8,
        }
        txt = build_archetype_profile_text(features)
        # Must surface every numeric field as a fact
        self.assertIn("$192", txt)
        self.assertIn("12 distinct", txt)
        self.assertIn("18 individual", txt)
        self.assertIn("48%", txt)
        self.assertIn("0.62", txt)
        self.assertIn("81%", txt)
        self.assertIn("56%", txt)
        # No role labels
        for forbidden in ("market maker", "whale", "expert", "novice", "predator"):
            self.assertNotIn(forbidden.lower(), txt.lower())

    def test_profile_text_handles_missing_accuracy(self):
        features = {
            "total_notional": 12.0, "tx_count": 2, "n_markets": 1,
            "top_market_share": 1.0, "mean_price": 0.5, "price_std": 0.0,
            "tail_trade_pct": 0.0, "log_active_days": -1.0,
            "past_accuracy": None, "n_resolved_prior": 0,
        }
        txt = build_archetype_profile_text(features)
        self.assertNotIn("accuracy", txt.lower())

    def test_build_population_deterministic(self):
        a = build_archetype_population(20, seed=42)
        b = build_archetype_population(20, seed=42)
        self.assertEqual(len(a), 20)
        self.assertEqual([x["wallet_addr"] for x in a],
                         [x["wallet_addr"] for x in b])

    def test_build_population_different_seeds_differ(self):
        a = build_archetype_population(50, seed=1)
        b = build_archetype_population(50, seed=2)
        # at least one wallet differs
        self.assertNotEqual(
            [x["wallet_addr"] for x in a],
            [x["wallet_addr"] for x in b],
        )


class EnvOverrideTest(unittest.TestCase):
    """v13 (Fix 7): POLYMETL_WALLET_CLUSTERS / POLYMETL_CLUSTER_PROFILES
    redirect the archetype sampler to a cutoff-conditioned table.
    """

    def setUp(self):
        self._saved_w = os.environ.pop("POLYMETL_WALLET_CLUSTERS", None)
        self._saved_p = os.environ.pop("POLYMETL_CLUSTER_PROFILES", None)
        ap.reset_caches()

    def tearDown(self):
        os.environ.pop("POLYMETL_WALLET_CLUSTERS", None)
        os.environ.pop("POLYMETL_CLUSTER_PROFILES", None)
        if self._saved_w is not None:
            os.environ["POLYMETL_WALLET_CLUSTERS"] = self._saved_w
        if self._saved_p is not None:
            os.environ["POLYMETL_CLUSTER_PROFILES"] = self._saved_p
        ap.reset_caches()

    def test_env_var_redirects_paths(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            # Fake clusters parquet
            df = pd.DataFrame({
                "wallet": ["0xfake1", "0xfake2"],
                "cluster": [0, 0],
                "total_notional": [123.0, 456.0],
                "tx_count": [3, 4],
                "n_markets": [1, 2],
                "top_market_share": [1.0, 0.5],
                "mean_price": [0.5, 0.4],
                "price_std": [0.1, 0.2],
                "tail_trade_pct": [0.0, 0.1],
                "log_active_days": [1.0, 2.0],
                "past_accuracy": [0.55, 0.6],
                "n_resolved_prior": [5, 6],
            })
            wc = tdp / "wallet_clusters_FAKE.parquet"
            cp = tdp / "cluster_profiles_FAKE.json"
            df.to_parquet(wc)
            cp.write_text(json.dumps({
                "K": 1, "seed": 42, "feat_cols": [],
                "clusters": {"0": {"size": 2, "pct": 1.0,
                                    "centroid": {}, "features": {}}},
            }))
            os.environ["POLYMETL_WALLET_CLUSTERS"] = str(wc)
            os.environ["POLYMETL_CLUSTER_PROFILES"] = str(cp)

            d = load_cluster_distribution()
            self.assertEqual(d["K"], 1)
            rng = random.Random(0)
            w = sample_wallet_in_cluster(0, rng)
            self.assertIn(w["wallet"], ("0xfake1", "0xfake2"))


if __name__ == "__main__":
    unittest.main()
