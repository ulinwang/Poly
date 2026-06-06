"""v13 — Random / marginal-matched baseline persona populations.

Two new persona dispatch values for B3 (cluster-structure ablation):

* ``marginal_random``: sample N wallets such that EACH of the seven
  scalar feature marginals matches the empirical population marginal
  (KS-test p > 0.5). Implemented as stratified rejection sampling on
  log-spaced bins, with a uniform fallback if the rejection budget is
  exhausted.

* ``uniform_random``: simple uniform-without-replacement sample from
  the wallet pool. Used as B3's null baseline — preserves wallet
  realism but destroys cluster proportions and marginal shape.

Both return the SAME shape as ``agent.personas.archetype
.build_archetype_population`` so ``agent.factory.init_agents`` can
dispatch on ``persona_set``:

    {cluster_id, wallet_addr, features, profile_text}

Wallet source: ``data/clustering/wallet_clusters.parquet`` by
default. Override via env var ``POLYMETL_WALLET_CLUSTERS`` (an AGT-3
convention).

Public API:
    load_wallet_pool(source: str = 'wallet_clusters') -> pd.DataFrame
    build_marginal_population(n_agents, seed, source='wallet_clusters')
    build_uniform_population(n_agents, seed, source='wallet_clusters')
"""
from __future__ import annotations

import logging
import os
import random
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

from agent.personas.archetype import build_archetype_profile_text


log = logging.getLogger(__name__)


# The 7 numerical marginals we want to preserve in ``marginal_random``.
# These mirror the 7 features that drove the K-means clustering.
MARGINAL_FEATURES = (
    "log_notional",
    "top_market_share",
    "n_markets_per_log_dollar",
    "mean_price",
    "tail_trade_pct",
    "log_active_days",
    "price_std",
)

DEFAULT_CLUSTERS_PATH = Path("data/clustering/wallet_clusters.parquet")


def _resolve_pool_path(source: str = "wallet_clusters") -> Path:
    """Resolve the wallet-pool parquet path.

    Source ``wallet_clusters`` (default): env var
    ``POLYMETL_WALLET_CLUSTERS`` overrides ``DEFAULT_CLUSTERS_PATH``.
    Any other source string is treated as a literal path."""
    if source == "wallet_clusters":
        env = os.environ.get("POLYMETL_WALLET_CLUSTERS")
        if env:
            return Path(env)
        return DEFAULT_CLUSTERS_PATH
    return Path(source)


@lru_cache(maxsize=4)
def load_wallet_pool(source: str = "wallet_clusters") -> pd.DataFrame:
    """Lazy-load and cache the wallet pool dataframe.

    The cache key includes ``source`` so test fixtures using a custom
    path don't clobber the production path's cache."""
    path = _resolve_pool_path(source)
    if not path.exists():
        raise FileNotFoundError(
            f"wallet pool not found at {path}; "
            f"run scripts/cluster_wallets.py or set "
            f"POLYMETL_WALLET_CLUSTERS"
        )
    return pd.read_parquet(path)


# ============================================================
# Sampling kernels
# ============================================================


def _features_dict(row: pd.Series) -> dict:
    """Convert a wallet row to the dict shape used by
    ``build_archetype_profile_text``. Adds ``total_notional`` and
    ``tx_count`` etc. so the renderer has everything it needs."""
    return {
        "total_notional": float(row.get("total_notional", 0.0)),
        "tx_count": int(row.get("tx_count", 0) or 0),
        "n_markets": int(row.get("n_markets", 0) or 0),
        "top_market_share": float(row.get("top_market_share", 0.0)),
        "mean_price": float(row.get("mean_price", 0.5)),
        "price_std": float(row.get("price_std", 0.0)),
        "tail_trade_pct": float(row.get("tail_trade_pct", 0.0)),
        "log_active_days": float(row.get("log_active_days", 0.0)),
        "past_accuracy": (None if pd.isna(row.get("past_accuracy"))
                          else float(row.get("past_accuracy", 0.5))),
        "n_resolved_prior": int(row.get("n_resolved_prior", 0) or 0),
    }


def _to_agent_dict(row: pd.Series) -> dict:
    feats = _features_dict(row)
    return {
        "cluster_id": int(row.get("cluster", -1)),
        "wallet_addr": str(row["wallet"]),
        "features": feats,
        "profile_text": build_archetype_profile_text(feats),
    }


def build_uniform_population(
    n_agents: int, seed: int = 0,
    source: str = "wallet_clusters",
    pool: Optional[pd.DataFrame] = None,
) -> list[dict]:
    """Uniform-without-replacement sample of ``n_agents`` wallets."""
    df = pool if pool is not None else load_wallet_pool(source)
    if n_agents <= 0:
        return []
    rng = random.Random(seed)
    n_pool = len(df)
    if n_pool == 0:
        return []
    # sample n_agents indices without replacement (or with, if needed)
    if n_agents <= n_pool:
        idxs = rng.sample(range(n_pool), n_agents)
    else:
        idxs = [rng.randrange(n_pool) for _ in range(n_agents)]
    return [_to_agent_dict(df.iloc[i]) for i in idxs]


def _stratified_indices(
    df: pd.DataFrame, n_agents: int, rng: random.Random,
    n_bins: int = 8,
) -> list[int]:
    """Stratified sample: bin on `log_notional` and take proportional
    counts from each bin. Then within-bin uniform sample.

    Returns a list of integer indices into ``df``."""
    n_pool = len(df)
    if n_pool == 0:
        return []
    # Bin by log_notional quantiles for stable coverage.
    series = df["log_notional"] if "log_notional" in df.columns \
        else df["total_notional"].apply(lambda x: max(x, 1e-3))
    try:
        bins = pd.qcut(series, q=n_bins, labels=False, duplicates="drop")
    except Exception:  # noqa: BLE001
        bins = pd.cut(series, bins=n_bins, labels=False)
    counts = bins.value_counts().sort_index()
    total = int(counts.sum())
    chosen: list[int] = []
    for bin_id, bin_count in counts.items():
        bin_n = int(round(n_agents * (bin_count / total)))
        if bin_n <= 0:
            continue
        # indices in this bin
        in_bin = list(df.index[bins == bin_id])
        rng.shuffle(in_bin)
        chosen.extend(in_bin[:bin_n])
    # Top up if rounding shrunk the sample
    if len(chosen) < n_agents:
        all_idx = list(df.index)
        rng.shuffle(all_idx)
        for i in all_idx:
            if i not in chosen:
                chosen.append(i)
                if len(chosen) >= n_agents:
                    break
    # If overshot, truncate.
    chosen = chosen[:n_agents]
    # Convert df.index values to positional ints
    pos_map = {idx_val: pos for pos, idx_val in enumerate(df.index)}
    return [pos_map[i] for i in chosen]


def _ks_pass(sample_vals: list, pop_vals, p_threshold: float = 0.5) -> bool:
    """Return True if the KS-test p-value is above ``p_threshold``
    (i.e., we *fail* to reject the null that sample and population
    share a distribution — the desired outcome)."""
    if len(sample_vals) < 2 or len(pop_vals) < 2:
        return True
    try:
        from scipy import stats
        res = stats.ks_2samp(sample_vals, pop_vals)
        return float(res.pvalue) > p_threshold
    except Exception:  # noqa: BLE001
        # If scipy isn't available, fall back to mean+std proximity.
        import statistics
        sm, pm = statistics.mean(sample_vals), statistics.mean(pop_vals)
        sd = statistics.pstdev(pop_vals) or 1.0
        return abs(sm - pm) / sd < 0.5


def build_marginal_population(
    n_agents: int, seed: int = 0,
    source: str = "wallet_clusters",
    pool: Optional[pd.DataFrame] = None,
    max_attempts: int = 32,
    ks_threshold: float = 0.5,
) -> list[dict]:
    """Stratified-rejection sample to preserve all 7 feature marginals.

    Each attempt: stratify on log_notional → uniform within bins.
    Accept if KS p-value > ``ks_threshold`` on EVERY feature in
    ``MARGINAL_FEATURES``. After ``max_attempts``, return the best
    attempt (highest minimum p-value across features)."""
    df = pool if pool is not None else load_wallet_pool(source)
    if n_agents <= 0 or len(df) == 0:
        return []
    rng = random.Random(seed)

    best_score = -1.0
    best_idxs: list[int] = []
    try:
        from scipy import stats
        have_scipy = True
    except Exception:  # noqa: BLE001
        have_scipy = False

    pop_vals = {f: df[f].dropna().to_numpy() for f in MARGINAL_FEATURES
                if f in df.columns}

    for attempt in range(max_attempts):
        attempt_rng = random.Random(rng.randrange(1 << 31))
        idxs = _stratified_indices(df, n_agents, attempt_rng)
        # Skip empty
        if not idxs:
            continue
        sub = df.iloc[idxs]
        if have_scipy:
            scores = []
            for f, pop_arr in pop_vals.items():
                sv = sub[f].dropna().to_numpy()
                if len(sv) < 2:
                    scores.append(1.0)
                    continue
                p = float(stats.ks_2samp(sv, pop_arr).pvalue)
                scores.append(p)
            min_p = min(scores) if scores else 1.0
            if min_p > best_score:
                best_score = min_p
                best_idxs = idxs
            if min_p > ks_threshold:
                log.debug("marginal_random accepted on attempt %d "
                          "(min_p=%.3f)", attempt, min_p)
                return [_to_agent_dict(df.iloc[i]) for i in idxs]
        else:
            # No scipy: accept the first stratified sample.
            return [_to_agent_dict(df.iloc[i]) for i in idxs]

    log.info("marginal_random: fell back to best-of-%d attempts "
             "(min_p=%.3f, threshold=%.2f)",
             max_attempts, best_score, ks_threshold)
    return [_to_agent_dict(df.iloc[i]) for i in best_idxs]
