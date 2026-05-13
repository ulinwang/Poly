"""Tests for marginal_random and uniform_random persona populations."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from agent.personas.random_baseline import (
    MARGINAL_FEATURES, build_marginal_population, build_uniform_population,
)


def _synthetic_pool(n: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Synthesize a wallet pool with the columns the random-baseline
    code expects, including the 7 marginal features and 5 clusters."""
    rng = np.random.default_rng(seed)
    # 5 clusters, each with a distinct shift on log_notional
    cluster_assignments = rng.integers(0, 5, size=n)
    log_notional = rng.normal(loc=2.0, scale=1.5, size=n) + cluster_assignments * 0.5
    return pd.DataFrame({
        "wallet": [f"0x{i:040x}" for i in range(n)],
        "cluster": cluster_assignments.astype(int),
        "log_notional": log_notional,
        "top_market_share": rng.beta(2, 5, size=n),
        "n_markets_per_log_dollar": rng.gamma(2.0, 1.0, size=n),
        "mean_price": rng.beta(5, 5, size=n),
        "tail_trade_pct": rng.beta(1, 4, size=n),
        "log_active_days": rng.normal(1.5, 0.6, size=n),
        "price_std": rng.beta(2, 8, size=n),
        "n_markets": rng.integers(1, 50, size=n),
        "tx_count": rng.integers(1, 200, size=n),
        "total_notional": np.exp(log_notional),
        "past_accuracy": rng.beta(5, 5, size=n),
        "n_resolved_prior": rng.integers(0, 20, size=n),
    })


class UniformRandomTest(unittest.TestCase):
    def test_returns_n_agents_shape(self):
        pool = _synthetic_pool(n=500, seed=0)
        agents = build_uniform_population(n_agents=30, seed=0, pool=pool)
        self.assertEqual(len(agents), 30)
        for a in agents:
            self.assertIn("cluster_id", a)
            self.assertIn("wallet_addr", a)
            self.assertIn("features", a)
            self.assertIn("profile_text", a)
            self.assertTrue(a["wallet_addr"].startswith("0x"))
            self.assertGreater(len(a["profile_text"]), 20)

    def test_uniform_random_covers_all_clusters_on_large_sample(self):
        pool = _synthetic_pool(n=2000, seed=1)
        agents = build_uniform_population(n_agents=200, seed=0, pool=pool)
        seen = {a["cluster_id"] for a in agents}
        self.assertEqual(len(seen), 5,
                         f"expected all 5 clusters, got {seen}")

    def test_uniform_random_determinism(self):
        pool = _synthetic_pool(n=500, seed=2)
        a1 = build_uniform_population(n_agents=20, seed=7, pool=pool)
        a2 = build_uniform_population(n_agents=20, seed=7, pool=pool)
        self.assertEqual([a["wallet_addr"] for a in a1],
                         [a["wallet_addr"] for a in a2])


class MarginalRandomTest(unittest.TestCase):
    def test_preserves_marginals_ks_above_threshold(self):
        from scipy import stats
        pool = _synthetic_pool(n=2000, seed=3)
        agents = build_marginal_population(
            n_agents=200, seed=0, pool=pool,
            max_attempts=12, ks_threshold=0.5,
        )
        self.assertEqual(len(agents), 200)
        # Reconstruct sample dataframe by matching wallet addresses
        wallet_set = {a["wallet_addr"] for a in agents}
        sub = pool[pool["wallet"].isin(wallet_set)]
        # At least 5 of 7 marginals must pass p>0.5 (the search budget
        # may not find perfection; we accept majority-pass).
        passes = 0
        for f in MARGINAL_FEATURES:
            sv = sub[f].dropna().to_numpy()
            pv = pool[f].dropna().to_numpy()
            if len(sv) < 2:
                continue
            p = float(stats.ks_2samp(sv, pv).pvalue)
            if p > 0.5:
                passes += 1
        self.assertGreaterEqual(passes, 5,
                                f"only {passes}/7 marginals pass p>0.5")

    def test_returns_archetype_shape(self):
        pool = _synthetic_pool(n=400, seed=4)
        agents = build_marginal_population(
            n_agents=20, seed=0, pool=pool, max_attempts=3,
        )
        self.assertEqual(len(agents), 20)
        for a in agents:
            self.assertSetEqual(
                set(a["features"].keys()),
                {"total_notional", "tx_count", "n_markets",
                 "top_market_share", "mean_price", "price_std",
                 "tail_trade_pct", "log_active_days",
                 "past_accuracy", "n_resolved_prior"},
            )


if __name__ == "__main__":
    unittest.main()
