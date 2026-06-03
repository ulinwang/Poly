"""Phase A.2: K-means clustering on the 7-feature matrix.

v13: hardened pipeline. See ``data/clustering/REVIEW.md`` §5.1/5.2.

- Compare ``StandardScaler`` and ``RobustScaler``; pick the variant
  with the higher silhouette under K=5 for the full sweep.
- Sweep K in {2,3,4,5,6,7,8}. For each K compute silhouette + 50-iter
  bootstrap Jaccard (subsample 100k, n_init=3).
- Pick the smallest K satisfying:
    (a) silhouette >= 0.20
    (b) median per-cluster Jaccard >= 0.75
    (c) every cluster >= 3% of population
  If no K qualifies, fall back to K=2 with a warning.
- Write cluster assignments + cluster_profiles + clustering_summary,
  each suffixed with the cutoff_iso so multiple cutoffs coexist.

CLI:
    uv run python -m scripts.clustering.cluster_wallets \\
        --features-parquet data/clustering/wallet_features_<ISO>.parquet \\
        --out-dir data/clustering
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import RobustScaler, StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)


FEAT_COLS = [
    "log_notional",          # activity scale
    "top_market_share",      # concentration on top market
    "n_markets_per_log_dollar",  # diversification per $
    "mean_price",            # preferred odds region (favorite/longshot)
    "tail_trade_pct",        # extreme-price appetite
    "log_active_days",       # tenure
    "price_std",             # price-range diversity
    "burstiness",            # v14: temporal clustering of trades (bounded -1..1)
]

# Supplementary cols that go into the persona prompt but NOT into clustering
PROMPT_COLS = ["n_markets", "tx_count", "total_notional",
               "past_accuracy", "n_resolved_prior"]

SEED = 42
SILH_SUBSAMPLE = 50_000   # silhouette is O(n²) memory
# v14: sweep 3..6 — K=2 is too coarse for behavioural roles, K>6 over-splits
# beyond the six-role taxonomy.
K_SWEEP = (3, 4, 5, 6)
BOOTSTRAP_ITERS = 50
BOOTSTRAP_SUBSAMPLE = 100_000
MIN_CLUSTER_PCT = 0.03
MIN_SILHOUETTE = 0.20
MIN_MEDIAN_JACCARD = 0.75
# v14: winsorize each feature at [p1, p99] before scaling so heavy-tailed
# outliers (whales, bots) cannot spawn sub-1% micro-clusters.
WINSOR_LO, WINSOR_HI = 1.0, 99.0

_SUFFIX_RE = re.compile(r"wallet_features_([0-9TZ]+)\.parquet$")


def _extract_suffix(features_path: Path) -> str:
    m = _SUFFIX_RE.search(features_path.name)
    if m:
        return m.group(1)
    s = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    print(f"WARN: could not parse cutoff suffix from {features_path.name}; "
          f"using {s}")
    return s


def _pairwise_jaccard(
    labels_full_on_sub: np.ndarray, labels_sub: np.ndarray,
    k_full: int, k_sub: int,
) -> np.ndarray:
    """For each cluster c in the full labels, find the best-matching
    cluster c' in the subsample labels and return Jaccard(c, c').
    Both arrays cover the same subsampled rows."""
    out = np.zeros(k_full, dtype=float)
    for c in range(k_full):
        a = labels_full_on_sub == c
        if a.sum() == 0:
            out[c] = 0.0
            continue
        best = 0.0
        for c2 in range(k_sub):
            b = labels_sub == c2
            inter = int(np.logical_and(a, b).sum())
            union = int(np.logical_or(a, b).sum())
            if union == 0:
                continue
            j = inter / union
            if j > best:
                best = j
        out[c] = best
    return out


def _bootstrap_jaccard(
    Xs: np.ndarray, labels_full: np.ndarray, k: int,
    n_iters: int, subsample: int, seed: int,
) -> np.ndarray:
    """Return (k,) median Jaccard per cluster across `n_iters`
    bootstrap subsamples."""
    rng = np.random.RandomState(seed)
    n = len(Xs)
    size = min(subsample, n)
    per_iter = np.zeros((n_iters, k), dtype=float)
    for it in range(n_iters):
        idx = rng.choice(n, size=size, replace=False)
        km = KMeans(n_clusters=k, n_init=3, random_state=seed + it)
        sub_labels = km.fit_predict(Xs[idx])
        per_iter[it] = _pairwise_jaccard(
            labels_full[idx], sub_labels, k_full=k, k_sub=k,
        )
    return np.median(per_iter, axis=0)


def _fit_and_score(
    Xs: np.ndarray, k: int, silh_idx: np.ndarray, seed: int,
) -> tuple[KMeans, np.ndarray, float]:
    km = KMeans(n_clusters=k, n_init=10, random_state=seed)
    labels = km.fit_predict(Xs)
    silh = float(silhouette_score(Xs[silh_idx], labels[silh_idx]))
    return km, labels, silh


def _select_k(sweep_records: list[dict]) -> tuple[int, bool]:
    """Apply the three-criterion rule. Returns (K, used_fallback).

    v14: among K that pass all three criteria, prefer the LARGEST for
    behavioural granularity (the old rule picked the smallest, which
    collapsed every modern market to K=2). If none qualify, fall back
    to the K with the highest silhouette.
    """
    valid = [
        r for r in sweep_records
        if r["silhouette"] >= MIN_SILHOUETTE
        and r["median_jaccard"] >= MIN_MEDIAN_JACCARD
        and r["min_cluster_pct"] >= MIN_CLUSTER_PCT
    ]
    if valid:
        return int(max(valid, key=lambda r: r["k"])["k"]), False
    best = max(sweep_records, key=lambda r: r["silhouette"])
    return int(best["k"]), True


def run(features_parquet: Path, out_dir: Path) -> dict:
    """Top-level entry. Returns the clustering_summary dict (also
    written to disk)."""
    print("=" * 70)
    print(f"Phase A.2: clustering — input={features_parquet}")
    print("=" * 70)
    t_start = time.time()

    df = pd.read_parquet(features_parquet)
    print(f"loaded: {len(df):,} wallets")

    X = np.array(df[FEAT_COLS].to_numpy(dtype=float), copy=True)
    # v14: fill NaN (e.g. burstiness undefined for very few trades) with the
    # column median, then winsorize at [p1, p99] to clip heavy-tailed outliers.
    col_med = np.nanmedian(X, axis=0)
    nan_idx = np.where(np.isnan(X))
    X[nan_idx] = np.take(col_med, nan_idx[1])
    lo = np.percentile(X, WINSOR_LO, axis=0)
    hi = np.percentile(X, WINSOR_HI, axis=0)
    X = np.clip(X, lo, hi)

    rng = np.random.RandomState(SEED)
    silh_idx = rng.choice(len(X), size=min(SILH_SUBSAMPLE, len(X)),
                          replace=False)

    # 5.1: compare scalers at K=5; use the higher-silhouette one.
    scaler_results: dict[str, dict] = {}
    for name, scaler in [
        ("standard", StandardScaler()),
        ("robust", RobustScaler()),
    ]:
        Xs = scaler.fit_transform(X)
        _, _, silh = _fit_and_score(Xs, k=5, silh_idx=silh_idx, seed=SEED)
        scaler_results[name] = {"scaler": scaler, "Xs": Xs, "k5_silh": silh}
        print(f"  scaler={name:>8}  K=5 silhouette={silh:.4f}")

    best_scaler_name = max(scaler_results, key=lambda n: scaler_results[n]["k5_silh"])
    Xs = scaler_results[best_scaler_name]["Xs"]
    scaler = scaler_results[best_scaler_name]["scaler"]
    print(f"→ using scaler='{best_scaler_name}' for the K sweep\n")

    print(f"sweeping K in {list(K_SWEEP)}; "
          f"silhouette on {len(silh_idx):,}-sample, "
          f"bootstrap Jaccard {BOOTSTRAP_ITERS}×{BOOTSTRAP_SUBSAMPLE:,}")
    sweep: list[dict] = []
    fits: dict[int, tuple[KMeans, np.ndarray]] = {}
    for k in K_SWEEP:
        t0 = time.time()
        km, labels, silh = _fit_and_score(Xs, k=k, silh_idx=silh_idx, seed=SEED)
        sizes = pd.Series(labels).value_counts(normalize=True).sort_values(ascending=False)
        min_pct = float(sizes.min())
        j_per_cluster = _bootstrap_jaccard(
            Xs, labels, k=k,
            n_iters=BOOTSTRAP_ITERS, subsample=BOOTSTRAP_SUBSAMPLE,
            seed=SEED,
        )
        med_jacc = float(np.median(j_per_cluster))
        elapsed = time.time() - t0
        sizes_str = " ".join(f"{p * 100:>4.1f}" for p in sizes)
        print(f"  K={k}  silh={silh:.4f}  med_J={med_jacc:.3f}  "
              f"min_pct={min_pct * 100:.2f}%  sizes(%)={sizes_str}  "
              f"[{elapsed:.1f}s]")
        sweep.append({
            "k": k, "silhouette": silh, "min_cluster_pct": min_pct,
            "median_jaccard": med_jacc,
            "per_cluster_jaccard": [float(x) for x in j_per_cluster],
            "cluster_sizes_pct": [float(p) for p in sizes.tolist()],
        })
        fits[k] = (km, labels)

    K, used_fallback = _select_k(sweep)
    if used_fallback:
        print(f"\nWARN: no K met all three criteria; falling back to K=2")
    selected = next(r for r in sweep if r["k"] == K)
    print(f"\n→ selected K={K} (silhouette={selected['silhouette']:.4f}, "
          f"median Jaccard={selected['median_jaccard']:.3f}, "
          f"min cluster={selected['min_cluster_pct'] * 100:.2f}%)")

    km, labels = fits[K]
    df = df.copy()
    df["cluster"] = labels

    suffix = _extract_suffix(features_parquet)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_clusters = out_dir / f"wallet_clusters_{suffix}.parquet"
    out_profiles = out_dir / f"cluster_profiles_{suffix}.json"
    out_summary = out_dir / f"clustering_summary_{suffix}.json"

    df[["wallet", "cluster"] + FEAT_COLS + PROMPT_COLS].to_parquet(
        out_clusters, compression="zstd",
    )
    print(f"wrote {out_clusters}")

    centroids_raw = scaler.inverse_transform(km.cluster_centers_)
    profiles = {
        "K": int(K), "seed": SEED, "feat_cols": FEAT_COLS,
        "scaler": best_scaler_name,
        "cutoff_iso_compact": suffix,
        "fallback_used": used_fallback,
        "clusters": {},
    }
    print("\n--- cluster centroids (raw feature space) ---")
    print(f"  {'cid':>3}  {'pct':>5}  " + "  ".join(f"{c[:9]:>10}" for c in FEAT_COLS))
    for cid in range(K):
        sub = df[df["cluster"] == cid]
        size = len(sub)
        pct = size / len(df) * 100
        print(f"  {cid:>3}  {pct:>4.1f}%  " + "  ".join(
            f"{centroids_raw[cid][i]:>10.3f}" for i in range(len(FEAT_COLS))
        ))
        feat_summary: dict = {}
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
    out_profiles.write_text(json.dumps(profiles, indent=2))
    print(f"wrote {out_profiles}")

    total_runtime = time.time() - t_start
    summary = {
        "K": int(K),
        "fallback_used": used_fallback,
        "scaler": best_scaler_name,
        "scaler_comparison_k5": {n: scaler_results[n]["k5_silh"]
                                  for n in scaler_results},
        "sweep": sweep,
        "selection_criteria": {
            "min_silhouette": MIN_SILHOUETTE,
            "min_median_jaccard": MIN_MEDIAN_JACCARD,
            "min_cluster_pct": MIN_CLUSTER_PCT,
        },
        "cutoff_iso_compact": suffix,
        "features_parquet": str(features_parquet),
        "total_runtime_s": round(total_runtime, 2),
    }
    out_summary.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out_summary}")
    print(f"\ntotal runtime: {total_runtime:.1f}s")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--features-parquet", required=True, type=Path)
    p.add_argument("--out-dir", default="data/clustering", type=Path)
    args = p.parse_args()
    run(features_parquet=args.features_parquet, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
