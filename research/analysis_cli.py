#!/usr/bin/env python3
"""On-chain market analysis CLI for the web "Data analysis" tab.

Usage:

    python research/analysis_cli.py <market-slug>

Resolves the slug to a ClickHouse ``condition_id`` and computes whatever
on-chain metrics are available from the ingested trade / holder tables:

  - trade count + total notional + unique wallets
  - a daily volume / trade-count time series
  - holder count and YES/NO holder split
  - top wallets by traded notional
  - a small maker/taker-style concentration summary (top-wallet share)

Everything is best-effort. The script NEVER raises on missing data: if
ClickHouse is unreachable, the market is unknown, or no trades have been
ingested, it prints ``{"available": false, "message": ...}`` and exits 0 so
the backend can surface a friendly empty state instead of a 500.

Output is a single JSON object on stdout.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone


def _err(message: str) -> dict:
    """Uniform 'no data' payload."""
    return {"available": False, "message": message}


def _to_ts(value) -> int | None:
    """Best-effort convert a ClickHouse datetime/row value to a unix int."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return int(value.timestamp())
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _day_key(value) -> str | None:
    """UTC date string (YYYY-MM-DD) for a datetime, or None."""
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return None


def analyze(slug: str) -> dict:
    """Compute on-chain analytics for ``slug``. Always returns a dict."""
    # Import inside the function so an import-time ClickHouse/driver problem
    # is reported as "unavailable" rather than crashing the process.
    try:
        from data.query.markets import get_market_meta
        from data.query.trades import get_trades
        from data.query.holders import get_top_holders
    except Exception as exc:  # pragma: no cover - defensive
        return _err(f"analysis backend unavailable: {exc}")

    # 1) Resolve slug -> market metadata (also probes the ClickHouse connection).
    try:
        meta = get_market_meta(slug)
    except Exception as exc:
        return _err(f"on-chain store unavailable: {exc}")

    if not meta:
        return _err(f"No ingested on-chain data for market '{slug}'.")

    condition_id = meta["condition_id"]

    # 2) Pull all trades for the market.
    try:
        trades = get_trades(condition_id)
    except Exception as exc:
        return _err(f"failed to read trades: {exc}")

    if not trades:
        return _err(
            f"Market '{slug}' is known but has no ingested trades yet."
        )

    # Rows: (trade_time, outcome_index, price, size, proxy_wallet)
    n_trades = len(trades)
    total_notional = 0.0
    wallets: set[str] = set()
    daily_vol: dict[str, float] = defaultdict(float)
    daily_cnt: dict[str, int] = defaultdict(int)
    wallet_notional: dict[str, float] = defaultdict(float)
    first_ts: int | None = None
    last_ts: int | None = None

    for trade_time, _oidx, price, size, wallet in trades:
        try:
            notional = float(price) * float(size)
        except (TypeError, ValueError):
            notional = 0.0
        total_notional += notional
        if wallet:
            wallets.add(wallet)
            wallet_notional[wallet] += notional
        day = _day_key(trade_time)
        if day:
            daily_vol[day] += notional
            daily_cnt[day] += 1
        ts = _to_ts(trade_time)
        if ts is not None:
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)

    # Volume / trade-count time series (chronological).
    volume_series = [
        {"date": day, "volume": round(daily_vol[day], 2), "trades": daily_cnt[day]}
        for day in sorted(daily_vol)
    ]

    # Top wallets by traded notional.
    top_wallets = sorted(
        wallet_notional.items(), key=lambda kv: kv[1], reverse=True
    )[:15]
    top_wallets_out = [
        {
            "wallet": w,
            "notional": round(n, 2),
            "share": round(n / total_notional, 4) if total_notional > 0 else 0.0,
        }
        for w, n in top_wallets
    ]

    # Concentration: share of total notional held by the top 1 / 5 / 10 wallets.
    sorted_notionals = sorted(wallet_notional.values(), reverse=True)

    def _top_share(k: int) -> float:
        if total_notional <= 0:
            return 0.0
        return round(sum(sorted_notionals[:k]) / total_notional, 4)

    concentration = {
        "top1_share": _top_share(1),
        "top5_share": _top_share(5),
        "top10_share": _top_share(10),
    }

    # 3) Holders (best-effort; missing table must not fail the whole analysis).
    holders_summary: dict | None = None
    try:
        holders = get_top_holders(condition_id, k=200)
        if holders:
            holder_wallets: set[str] = set()
            yes_holders: set[str] = set()
            no_holders: set[str] = set()
            for wallet, outcome_index, _amt, _dn in holders:
                if not wallet:
                    continue
                holder_wallets.add(wallet)
                try:
                    oidx = int(outcome_index)
                except (TypeError, ValueError):
                    oidx = -1
                if oidx == 0:
                    yes_holders.add(wallet)
                elif oidx == 1:
                    no_holders.add(wallet)
            holders_summary = {
                "n_holders": len(holder_wallets),
                "yes_holders": len(yes_holders),
                "no_holders": len(no_holders),
            }
    except Exception:
        holders_summary = None

    return {
        "available": True,
        "slug": slug,
        "condition_id": condition_id,
        "question": meta.get("question", ""),
        "outcomes": meta.get("outcomes", ["Yes", "No"]),
        "winning_idx": meta.get("winning_idx", -1),
        "metrics": {
            "n_trades": n_trades,
            "total_notional": round(total_notional, 2),
            "unique_wallets": len(wallets),
            "first_trade_ts": first_ts,
            "last_trade_ts": last_ts,
        },
        "volume_series": volume_series,
        "top_wallets": top_wallets_out,
        "concentration": concentration,
        "holders": holders_summary,
    }


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        json.dump(_err("usage: analysis_cli.py <market-slug>"), sys.stdout)
        print()
        return
    slug = sys.argv[1].strip()
    try:
        result = analyze(slug)
    except Exception as exc:  # final safety net: never crash the spawn
        result = _err(f"unexpected analysis error: {exc}")
    json.dump(result, sys.stdout, ensure_ascii=False, default=str)
    print()


if __name__ == "__main__":
    main()
