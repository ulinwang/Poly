"""Phase A.1: compute 7 orthogonal-ish behavioral features per wallet
from the full 1.42M-wallet Polymarket population, save to parquet."""
from __future__ import annotations

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
        toUInt32(toUnixTimestamp(max(trade_time)) - toUnixTimestamp(min(trade_time))) AS span_secs
    FROM polymetl.dataapi_trades
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
    ) AS mr ON mr.condition_id = t.condition_id
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

OUT = Path("/Users/moonshot/Projects/Poly/polymetl/data/clustering/wallet_features_full.parquet")

print(f"=" * 70)
print(f"Phase A.1: computing 7-feature matrix for full Polymarket population")
print(f"=" * 70)
t0 = time.time()
ch = get_ch()
rows = ch.client.execute(SQL)
t1 = time.time()
print(f"SQL: {len(rows):,} rows in {t1-t0:.1f}s")

cols = ["wallet", "log_notional", "top_market_share", "n_markets_per_log_dollar",
        "mean_price", "tail_trade_pct", "log_active_days", "price_std",
        "n_markets", "tx_count", "total_notional",
        "past_accuracy", "n_resolved_prior"]
df = pd.DataFrame(rows, columns=cols)
print(f"\n--- 描述统计 ---")
print(df[["log_notional", "top_market_share", "n_markets_per_log_dollar",
          "mean_price", "tail_trade_pct", "log_active_days", "price_std",
          "past_accuracy"]].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).round(3))

print(f"\n--- 相关性矩阵(7 个 clustering 特征)---")
feat_cols = ["log_notional", "top_market_share", "n_markets_per_log_dollar",
             "mean_price", "tail_trade_pct", "log_active_days", "price_std"]
corr = df[feat_cols].corr()
# Show only abs > 0.4 for readability
for i, a in enumerate(feat_cols):
    line = f"  {a:<28}"
    for j, b in enumerate(feat_cols):
        v = corr.iloc[i, j]
        if i == j:
            line += "   .   "
        elif abs(v) > 0.4:
            line += f"{v:>+6.2f} "
        else:
            line += f"({v:>+5.2f})"
    print(line)

# Save
OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(OUT, compression="zstd")
print(f"\nwrote {OUT} ({OUT.stat().st_size/1024/1024:.1f} MB, {len(df):,} rows)")
