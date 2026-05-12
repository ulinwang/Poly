"""v10 — Archetype-based persona sampling.

For each new agent, we sample an archetype from the empirical
cluster distribution (K-means K=5, fitted on 1.19M Polymarket
wallets), then sample a concrete wallet from that cluster, and use
its ACTUAL feature values to render a persona profile_text.

No role labels. No hand-tuned templates. The persona profile is a
factual restatement of the wallet's measured behavioral fingerprint:
the LLM agent infers its own trading style at decision time.

Public API:
    load_cluster_distribution()      → (probs, profiles_json)
    sample_archetype(rng)            → cluster_id
    sample_wallet_in_cluster(cid)    → dict of wallet features
    build_archetype_profile_text(features) → str (for AgentInit.profile_text)
    build_archetype_population(n, seed=0) → list[dict] for factory
"""
from __future__ import annotations

import json
import math
import random
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd


CLUSTERING_DIR = Path("data/clustering")
PROFILES_PATH = CLUSTERING_DIR / "cluster_profiles.json"
WALLETS_PATH = CLUSTERING_DIR / "wallet_clusters.parquet"


@lru_cache(maxsize=1)
def load_cluster_distribution() -> dict:
    """Read the K-means cluster_profiles.json artifact."""
    if not PROFILES_PATH.exists():
        raise FileNotFoundError(
            f"missing {PROFILES_PATH}; run scripts/cluster_wallets.py first"
        )
    return json.loads(PROFILES_PATH.read_text())


@lru_cache(maxsize=1)
def _wallet_pool() -> pd.DataFrame:
    """Lazy-load the full 1.19M-wallet cluster assignment table."""
    return pd.read_parquet(WALLETS_PATH)


def sample_archetype(rng: random.Random) -> int:
    """Sample one cluster id according to its empirical probability."""
    profiles = load_cluster_distribution()
    K = profiles["K"]
    weights = [profiles["clusters"][str(c)]["pct"] for c in range(K)]
    return rng.choices(range(K), weights=weights, k=1)[0]


def sample_wallet_in_cluster(cluster_id: int, rng: random.Random) -> dict:
    """Pick one random wallet from `cluster_id` and return its full
    feature row as a dict."""
    pool = _wallet_pool()
    sub = pool[pool["cluster"] == cluster_id]
    if len(sub) == 0:
        raise ValueError(f"no wallets in cluster {cluster_id}")
    idx = rng.randrange(len(sub))
    return sub.iloc[idx].to_dict()


def build_archetype_profile_text(features: dict) -> str:
    """Render a wallet's measured features as factual persona text.

    No role labels, no archetype names — only numbers and units.
    The LLM at decision time will infer the implicit trading style.
    """
    notional = float(features.get("total_notional", 0.0))
    tx_count = int(features.get("tx_count", 0))
    n_markets = int(features.get("n_markets", 0))
    top_share = float(features.get("top_market_share", 0.0))
    mean_price = float(features.get("mean_price", 0.5))
    price_std = float(features.get("price_std", 0.0))
    tail_pct = float(features.get("tail_trade_pct", 0.0))
    active_days = max(1.0, 10.0 ** float(features.get("log_active_days", 0.0)))

    past_acc = features.get("past_accuracy")
    n_resolved = int(features.get("n_resolved_prior", 0) or 0)

    lines = [
        f"You have traded ${notional:,.0f} of notional volume across "
        f"{n_markets} distinct Polymarket events over the past "
        f"{active_days:.0f} day{'s' if active_days != 1 else ''} on the platform.",

        f"This volume came from {tx_count} individual trades; "
        f"{top_share*100:.0f}% of your capital concentrated on your "
        f"single most-traded market.",

        f"Across your historical trades, the price you bought at "
        f"averaged {mean_price:.2f} (standard deviation {price_std:.2f}), "
        f"and {tail_pct*100:.0f}% of your trades were at "
        f"extreme prices (below 0.10 or above 0.90).",
    ]

    if past_acc is not None and not (
        isinstance(past_acc, float) and math.isnan(past_acc)
    ):
        lines.append(
            f"Your capital-weighted prediction accuracy on "
            f"{n_resolved} resolved markets is {float(past_acc)*100:.0f}%."
        )
    elif n_resolved > 0:
        lines.append(
            f"You have participated in {n_resolved} resolved markets, "
            f"but your sample size is too small to report a stable "
            f"win rate."
        )

    return " ".join(lines)


def build_archetype_population(
    n_agents: int, seed: int = 0,
) -> list[dict]:
    """Build n_agents persona specs by sampling archetypes from the
    empirical distribution and pulling concrete wallets per cluster.

    Returns: list of dicts, one per agent, with keys
        cluster_id, wallet_addr, features (the raw row), profile_text.
    """
    rng = random.Random(seed)
    out: list[dict] = []
    for _ in range(n_agents):
        cid = sample_archetype(rng)
        row = sample_wallet_in_cluster(cid, rng)
        feats = {k: row[k] for k in (
            "total_notional", "tx_count", "n_markets", "top_market_share",
            "mean_price", "price_std", "tail_trade_pct", "log_active_days",
            "past_accuracy", "n_resolved_prior",
        )}
        out.append({
            "cluster_id": cid,
            "wallet_addr": str(row["wallet"]),
            "features": feats,
            "profile_text": build_archetype_profile_text(feats),
        })
    return out
