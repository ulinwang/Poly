"""Phase A.2: K-means clustering on the 7-feature matrix.

Pipeline:
- Z-score standardize the 7 clustering features
- Run K-means for K in {3..10}, compute silhouette on a 50k subsample
- Run GMM with same K range, compute BIC on a 50k subsample
- Pick the K that maximizes silhouette while keeping cluster sizes >= 2%
- Save cluster assignment + cluster centroids (in raw feature space) + summary stats
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path("/Users/moonshot/Projects/Poly/polymetl/data/clustering")
IN = ROOT / "wallet_features_full.parquet"
OUT_CLUSTERS = ROOT / "wallet_clusters.parquet"
OUT_PROFILES = ROOT / "cluster_profiles.json"

FEAT_COLS = [
    "log_notional",          # activity scale
    "top_market_share",      # concentration on top market
    "n_markets_per_log_dollar",  # diversification per $
    "mean_price",            # preferred odds region
    "tail_trade_pct",        # longshot appetite
    "log_active_days",       # tenure
    "price_std",             # price-range diversity
]

# Supplementary cols that go into the persona prompt but NOT into clustering
PROMPT_COLS = ["n_markets", "tx_count", "total_notional",
               "past_accuracy", "n_resolved_prior"]

SEED = 42
SILH_SUBSAMPLE = 50_000   # silhouette is O(n²) memory


def main():
    print("=" * 70)
    print("Phase A.2: clustering 1.19M wallets")
    print("=" * 70)
    df = pd.read_parquet(IN)
    print(f"loaded: {len(df):,} wallets")

    X = df[FEAT_COLS].values
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    print(f"standardized: mean ~0, std ~1 across {Xs.shape[1]} features")

    rng = np.random.RandomState(SEED)
    silh_idx = rng.choice(len(Xs), size=min(SILH_SUBSAMPLE, len(Xs)), replace=False)

    print(f"\nsweeping K = 3..10, silhouette on {len(silh_idx):,} subsample:")
    print(f"  {'K':>3}  {'silhouette':>11}  {'inertia':>12}  {'GMM BIC':>14}  cluster sizes (%)")
    results = []
    best_assignments_by_k = {}
    for k in range(3, 11):
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED)
        labels = km.fit_predict(Xs)
        silh = silhouette_score(Xs[silh_idx], labels[silh_idx])
        gmm = GaussianMixture(n_components=k, covariance_type="full",
                              random_state=SEED, max_iter=200,
                              n_init=1)
        gmm.fit(Xs[silh_idx])
        bic = gmm.bic(Xs[silh_idx])
        sizes = pd.Series(labels).value_counts(normalize=True).sort_values(ascending=False)
        sizes_str = " ".join(f"{p*100:>4.1f}" for p in sizes)
        print(f"  {k:>3}  {silh:>11.4f}  {km.inertia_:>12.0f}  {bic:>14.0f}  {sizes_str}")
        results.append({"k": k, "silhouette": float(silh), "inertia": float(km.inertia_),
                        "bic": float(bic), "min_cluster_pct": float(sizes.min())})
        best_assignments_by_k[k] = (labels, km, km.cluster_centers_)

    # Pick K: maximize silhouette AND keep min_cluster_pct >= 0.03 (3%)
    candidates = [r for r in results if r["min_cluster_pct"] >= 0.03]
    if not candidates:
        candidates = results
    best = max(candidates, key=lambda r: r["silhouette"])
    K = best["k"]
    print(f"\n→ selected K = {K} (silhouette={best['silhouette']:.4f}, "
          f"smallest cluster = {best['min_cluster_pct']*100:.1f}%)")

    # Save full assignment
    labels, km, centroids_z = best_assignments_by_k[K]
    df["cluster"] = labels
    df[["wallet", "cluster"] + FEAT_COLS + PROMPT_COLS].to_parquet(
        OUT_CLUSTERS, compression="zstd",
    )
    print(f"wrote {OUT_CLUSTERS}")

    # Build cluster profile JSON: raw-feature centroid + percentile stats + size
    centroids_raw = scaler.inverse_transform(centroids_z)
    profiles = {"K": int(K), "seed": SEED, "feat_cols": FEAT_COLS, "clusters": {}}
    print(f"\n--- cluster centroids (raw feature space) ---")
    print(f"  {'cid':>3}  {'pct':>5}  " + "  ".join(f"{c[:9]:>10}" for c in FEAT_COLS))
    for cid in range(K):
        mask = df["cluster"] == cid
        sub = df[mask]
        size = len(sub)
        pct = size / len(df) * 100
        print(f"  {cid:>3}  {pct:>4.1f}%  " + "  ".join(f"{centroids_raw[cid][i]:>10.3f}" for i in range(len(FEAT_COLS))))

        # Per-cluster percentile summary for every feature (clustering + prompt)
        feat_summary = {}
        for col in FEAT_COLS + PROMPT_COLS:
            if col == "past_accuracy":
                v = sub[col].dropna()
                if len(v) > 10:
                    feat_summary[col] = {
                        "n": int(len(v)),
                        "p25": float(v.quantile(0.25)),
                        "p50": float(v.quantile(0.50)),
                        "p75": float(v.quantile(0.75)),
                    }
                else:
                    feat_summary[col] = {"n": int(len(v)), "note": "n<10, unreliable"}
            else:
                v = sub[col]
                feat_summary[col] = {
                    "p25": float(v.quantile(0.25)),
                    "p50": float(v.quantile(0.50)),
                    "p75": float(v.quantile(0.75)),
                }
        profiles["clusters"][str(cid)] = {
            "size": int(size),
            "pct": float(size / len(df)),
            "centroid": {col: float(centroids_raw[cid][i]) for i, col in enumerate(FEAT_COLS)},
            "features": feat_summary,
        }

    OUT_PROFILES.write_text(json.dumps(profiles, indent=2))
    print(f"\nwrote {OUT_PROFILES}")

    # Sample 5 wallets per cluster for sanity
    print(f"\n--- 5 wallet examples per cluster ---")
    for cid in range(K):
        sub = df[df["cluster"] == cid].head(3)
        print(f"\ncluster {cid} ({len(df[df['cluster']==cid]):,} wallets):")
        for _, r in sub.iterrows():
            acc = "-" if pd.isna(r["past_accuracy"]) else f"{r['past_accuracy']:.2f}"
            print(f"  {r['wallet'][:10]}…  notional=${r['total_notional']:>10,.0f}  "
                  f"tx={r['tx_count']:>4}  mkts={r['n_markets']:>3}  "
                  f"top_share={r['top_market_share']:.2f}  mean_price={r['mean_price']:.2f}  "
                  f"tail%={r['tail_trade_pct']*100:.0f}  acc={acc}")


if __name__ == "__main__":
    main()
