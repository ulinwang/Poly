"""Unit tests for scripts/clustering/cluster_wallets.py.

We build a small synthetic 3-cluster blob dataset and verify:
  - _select_k applies the three-criterion rule correctly
  - end-to-end ``run`` writes the three artifacts with cutoff suffix
  - The fallback to K=2 fires when no K meets all criteria
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.clustering import cluster_wallets as cw


def _make_features_parquet(path: Path, n_per: int = 500, seed: int = 42):
    """Three well-separated blobs in 7-D, big enough to exceed
    silhouette/jaccard thresholds for K=3."""
    rng = np.random.RandomState(seed)
    centers = np.array([
        [1.0, 0.1, 0.5, 0.4, 0.05, 1.0, 0.1],
        [4.0, 0.6, 2.0, 0.5, 0.40, 2.5, 0.3],
        [2.5, 0.3, 5.0, 0.6, 0.15, 0.5, 0.2],
    ])
    parts = []
    for c in centers:
        parts.append(rng.normal(loc=c, scale=0.05, size=(n_per, 7)))
    X = np.vstack(parts)
    df = pd.DataFrame(X, columns=cw.FEAT_COLS)
    df.insert(0, "wallet", [f"0x{i:040x}" for i in range(len(df))])
    df["n_markets"] = 3
    df["tx_count"] = 10
    df["total_notional"] = 100.0
    df["past_accuracy"] = 0.5
    df["n_resolved_prior"] = 5
    # Suffix that the script's regex will extract.
    out = path / "wallet_features_20230523T153721Z.parquet"
    df.to_parquet(out, compression="zstd")
    return out


class SelectKTest(unittest.TestCase):
    def test_picks_smallest_qualifying_k(self):
        sweep = [
            {"k": 2, "silhouette": 0.18, "median_jaccard": 0.80, "min_cluster_pct": 0.40},
            {"k": 3, "silhouette": 0.25, "median_jaccard": 0.80, "min_cluster_pct": 0.30},
            {"k": 4, "silhouette": 0.28, "median_jaccard": 0.85, "min_cluster_pct": 0.20},
        ]
        K, used_fallback = cw._select_k(sweep)
        self.assertEqual(K, 3)
        self.assertFalse(used_fallback)

    def test_fallback_when_none_qualify(self):
        sweep = [
            {"k": 2, "silhouette": 0.10, "median_jaccard": 0.60, "min_cluster_pct": 0.40},
            {"k": 3, "silhouette": 0.15, "median_jaccard": 0.50, "min_cluster_pct": 0.30},
        ]
        K, used_fallback = cw._select_k(sweep)
        self.assertEqual(K, 2)
        self.assertTrue(used_fallback)


class JaccardTest(unittest.TestCase):
    def test_perfect_match_returns_ones(self):
        labels_full_on_sub = np.array([0, 0, 1, 1, 2, 2])
        labels_sub = np.array([0, 0, 1, 1, 2, 2])
        out = cw._pairwise_jaccard(labels_full_on_sub, labels_sub,
                                    k_full=3, k_sub=3)
        np.testing.assert_array_almost_equal(out, [1.0, 1.0, 1.0])

    def test_permutation_match_returns_ones(self):
        labels_full_on_sub = np.array([0, 0, 1, 1, 2, 2])
        labels_sub = np.array([2, 2, 0, 0, 1, 1])
        out = cw._pairwise_jaccard(labels_full_on_sub, labels_sub,
                                    k_full=3, k_sub=3)
        np.testing.assert_array_almost_equal(out, [1.0, 1.0, 1.0])


class EndToEndRunTest(unittest.TestCase):
    def test_run_produces_three_artifacts_with_suffix(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            features_path = _make_features_parquet(tdp, n_per=500)
            # Patch globals to make the test fast.
            orig_iters = cw.BOOTSTRAP_ITERS
            orig_sub = cw.BOOTSTRAP_SUBSAMPLE
            orig_silh = cw.SILH_SUBSAMPLE
            orig_sweep = cw.K_SWEEP
            try:
                cw.BOOTSTRAP_ITERS = 5
                cw.BOOTSTRAP_SUBSAMPLE = 400
                cw.SILH_SUBSAMPLE = 400
                cw.K_SWEEP = (2, 3, 4)
                summary = cw.run(features_parquet=features_path,
                                 out_dir=tdp)
            finally:
                cw.BOOTSTRAP_ITERS = orig_iters
                cw.BOOTSTRAP_SUBSAMPLE = orig_sub
                cw.SILH_SUBSAMPLE = orig_silh
                cw.K_SWEEP = orig_sweep

            suffix = "20230523T153721Z"
            self.assertTrue((tdp / f"wallet_clusters_{suffix}.parquet").exists())
            self.assertTrue((tdp / f"cluster_profiles_{suffix}.json").exists())
            self.assertTrue((tdp / f"clustering_summary_{suffix}.json").exists())

            # Three well-separated blobs → both K=2 and K=3 qualify;
            # the rule picks the SMALLEST qualifying K (=2) per
            # data/clustering/REVIEW.md §5.2.
            self.assertIn(summary["K"], (2, 3))
            self.assertFalse(summary["fallback_used"])
            # Sanity: every cluster meaningfully populated.
            profiles = json.loads(
                (tdp / f"cluster_profiles_{suffix}.json").read_text()
            )
            sizes = [profiles["clusters"][str(c)]["pct"]
                     for c in range(profiles["K"])]
            for s in sizes:
                self.assertGreater(s, 0.10)


if __name__ == "__main__":
    unittest.main()
