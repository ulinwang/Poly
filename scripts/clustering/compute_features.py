"""Phase A.1: compute 7 orthogonal-ish behavioral features per wallet
from the Polymarket trade population, save to parquet.

v13: time-cutoff aware. Every SELECT over ``polymetl.dataapi_trades`` is
``AND toUnixTimestamp(trade_time) < cutoff_ts``-filtered, and the
``markets_resolved`` join (for ``past_accuracy``) is filtered by
``mr.end_date < cutoff``. The output filename encodes the cutoff so
multiple cutoffs can coexist on disk. See ``docs/v13/DATA_HYGIENE_AUDIT.md``
findings L-1, L-5, L-9.
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path

import pandas as pd

from data.query._ch import get_ch


SQL = """
WITH per_market AS (
    -- (wallet, market) → market-level notional. Used by top_market_share + n_markets.
    SELECT
        proxy_wallet AS pw,
        condition_id,
        sum(price * size) AS market_notional
    FROM polymetl.dataapi_trades
    WHERE toUnixTimestamp(trade_time) < %(cutoff_ts)s
    GROUP BY pw, condition_id
),
agg_per_wallet AS (
    SELECT
        pw,
        sum(market_notional) AS total_notional,
        max(market_notional) AS top_notional,
        count() AS n_markets
    FROM per_market
    GROUP BY pw
),
trade_stats AS (
    SELECT
        proxy_wallet AS pw,
        count() AS tx_count,
        avg(price) AS mean_price,
        stddevPop(price) AS price_std,
        countIf(price < 0.1 OR price > 0.9) / count() AS tail_trade_pct,
        toUInt32(toUnixTimestamp(max(trade_time)) - toUnixTimestamp(min(trade_time))) AS span_secs,
        -- per-trade notional dispersion: std/mean of |price*size|
        stddevPop(price * size) / greatest(avg(price * size), 1e-9) AS trade_size_cv,
        -- inter-trade gap stats for burstiness
        arrayReduce('avg', arrayDifference(arraySort(groupArray(toUnixTimestamp(trade_time))))) AS gap_mean,
        arrayReduce('stddevPop', arrayDifference(arraySort(groupArray(toUnixTimestamp(trade_time))))) AS gap_std
    FROM polymetl.dataapi_trades
    WHERE toUnixTimestamp(trade_time) < %(cutoff_ts)s
    GROUP BY pw
),
acc AS (
    SELECT
        t.proxy_wallet AS pw,
        sum(t.price * t.size) AS resolved_notional,
        sumIf(t.price * t.size, t.outcome_index = mr.winning_idx) AS won_notional,
        uniqExact(t.condition_id) AS n_resolved
    FROM polymetl.dataapi_trades AS t
    INNER JOIN (
        SELECT condition_id, winning_idx FROM polymetl.markets_resolved FINAL
        WHERE winning_idx >= 0
          AND end_date < toDateTime(%(cutoff_ts)s)
    ) AS mr ON mr.condition_id = t.condition_id
    WHERE toUnixTimestamp(t.trade_time) < %(cutoff_ts)s
    GROUP BY pw
    HAVING resolved_notional > 0
)
SELECT
    apw.pw AS wallet,
    -- core 7 features
    log10(greatest(apw.total_notional, 0.01)) AS log_notional,
    apw.top_notional / apw.total_notional AS top_market_share,
    apw.n_markets / greatest(log10(greatest(apw.total_notional, 1.0)), 0.1)
        AS n_markets_per_log_dollar,
    ts.mean_price AS mean_price,
    ts.tail_trade_pct AS tail_trade_pct,
    log10(greatest(ts.span_secs / 86400.0, 0.01)) AS log_active_days,
    ts.price_std AS price_std,
    -- 3 behavioural-style features (v14): trade frequency, size irregularity,
    -- temporal burstiness. All describe *style*, never trade direction.
    ts.tx_count / greatest(ts.span_secs / 86400.0, 0.01) AS trades_per_day,
    ts.trade_size_cv AS trade_size_cv,
    (ts.gap_std - ts.gap_mean) / greatest(ts.gap_std + ts.gap_mean, 1e-9)
        AS burstiness,
    -- supplementary (NOT in clustering, used only in prompt)
    apw.n_markets AS n_markets,
    ts.tx_count AS tx_count,
    apw.total_notional AS total_notional,
    if(acc.n_resolved >= 5, acc.won_notional / acc.resolved_notional, NULL)
        AS past_accuracy,
    acc.n_resolved AS n_resolved_prior
FROM agg_per_wallet AS apw
INNER JOIN trade_stats AS ts USING (pw)
LEFT JOIN acc USING (pw)
WHERE
    apw.total_notional > 0
    AND ts.tx_count >= 2  -- need at least 2 trades to compute std + price std
"""


COLS = [
    "wallet", "log_notional", "top_market_share", "n_markets_per_log_dollar",
    "mean_price", "tail_trade_pct", "log_active_days", "price_std",
    "trades_per_day", "trade_size_cv", "burstiness",
    "n_markets", "tx_count", "total_notional",
    "past_accuracy", "n_resolved_prior",
]

CLUSTER_FEAT_COLS = [
    "log_notional", "top_market_share", "n_markets_per_log_dollar",
    "mean_price", "tail_trade_pct", "log_active_days", "price_std",
    "trades_per_day", "trade_size_cv", "burstiness",
]


def cutoff_iso_compact(cutoff_ts: int) -> str:
    """Compact ISO suffix for filenames: YYYYMMDDTHHMMSSZ."""
    return dt.datetime.utcfromtimestamp(int(cutoff_ts)).strftime("%Y%m%dT%H%M%SZ")


def _resolve_cutoff(args: argparse.Namespace) -> int:
    if args.cutoff_ts is not None and args.cutoff_iso is not None:
        raise SystemExit("--cutoff-ts and --cutoff-iso are mutually exclusive")
    if args.cutoff_ts is not None:
        return int(args.cutoff_ts)
    if args.cutoff_iso is not None:
        s = args.cutoff_iso.replace("Z", "+00:00")
        d = dt.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return int(d.timestamp())
    raise SystemExit("one of --cutoff-ts or --cutoff-iso is required")


def compute(
    cutoff_ts: int, out_dir: Path, ch=None,
) -> Path:
    """Run the SQL + write parquet. Returns the output path.

    Split out from ``main`` so unit tests can inject a stubbed ``ch``
    object and avoid a real ClickHouse connection.
    """
    print("=" * 70)
    iso = dt.datetime.utcfromtimestamp(cutoff_ts).isoformat() + "Z"
    print(f"Phase A.1: feature matrix, cutoff_ts={cutoff_ts} ({iso})")
    print("=" * 70)
    ch = get_ch(ch)
    t0 = time.time()
    rows = ch.client.execute(SQL, {"cutoff_ts": int(cutoff_ts)})
    t1 = time.time()
    print(f"SQL: {len(rows):,} rows in {t1 - t0:.1f}s")

    df = pd.DataFrame(rows, columns=COLS)

    if len(df) > 0:
        n10 = int((df["tx_count"] >= 10).sum())
        q = df["total_notional"].quantile([0.25, 0.5, 0.75])
        print(
            f"summary: n={len(df):,}  pct_N>=10={n10 / len(df):.3f}  "
            f"total_notional p25/p50/p75=${q.loc[0.25]:,.0f}/"
            f"${q.loc[0.5]:,.0f}/${q.loc[0.75]:,.0f}"
        )

        print("\n--- descriptive stats ---")
        cluster_cols = [c for c in CLUSTER_FEAT_COLS if c in df.columns]
        with pd.option_context("display.width", 160, "display.max_columns", 20):
            print(df[cluster_cols + ["past_accuracy"]].describe(
                percentiles=[0.1, 0.25, 0.5, 0.75, 0.9],
            ).round(3))

    suffix = cutoff_iso_compact(cutoff_ts)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"wallet_features_{suffix}.parquet"
    df.to_parquet(out_path, compression="zstd")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"\nwrote {out_path} ({size_mb:.1f} MB, {len(df):,} rows)")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cutoff-ts", type=int, default=None,
                   help="unix timestamp; trades with trade_time < cutoff_ts kept")
    p.add_argument("--cutoff-iso", type=str, default=None,
                   help="ISO-8601 cutoff (mutually exclusive with --cutoff-ts)")
    p.add_argument("--out-dir", default="data/clustering",
                   help="output directory for the parquet file")
    args = p.parse_args()

    cutoff_ts = _resolve_cutoff(args)
    out_dir = Path(args.out_dir)
    compute(cutoff_ts=cutoff_ts, out_dir=out_dir)


if __name__ == "__main__":
    main()
