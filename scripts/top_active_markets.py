"""
Show the top N active Polymarket markets by 24-hour CLOB volume,
along with parent event grouping (events.ticker).

This script hits the live Gamma API directly (no ClickHouse needed),
so it can be used to spot-check the data even before the puller has
written to the database.

Usage:
    uv run python scripts/top_active_markets.py
    uv run python scripts/top_active_markets.py --pages 4 --top 50
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.sources.gamma_api import fetch_markets_page  # noqa: E402


def _ticker(m: dict) -> str:
    evs = m.get("events") or []
    return evs[0].get("ticker") if evs else "(none)"


def _v24(m: dict) -> float:
    try:
        return float(m.get("volume24hrClob") or 0)
    except (TypeError, ValueError):
        return 0.0


def _yes_price(m: dict) -> float | None:
    raw = m.get("outcomePrices") or "[]"
    try:
        prices = json.loads(raw) if isinstance(raw, str) else raw
        return float(prices[0]) if prices else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=2, help="how many 500-market pages to scan")
    parser.add_argument("--top", type=int, default=30, help="how many markets to print")
    args = parser.parse_args()

    all_markets: list[dict] = []
    for i in range(args.pages):
        page = fetch_markets_page(limit=500, offset=i * 500, closed=False)
        all_markets.extend(page)
        if len(page) < 500:
            break

    active = [m for m in all_markets if m.get("active") and not m.get("closed")]
    print(f"fetched {len(all_markets)} markets, {len(active)} active\n")

    print("=== top 25 event groups by market count ===")
    for ticker, n in Counter(_ticker(m) for m in active).most_common(25):
        print(f"  {n:>4}  {ticker}")
    print()

    active.sort(key=_v24, reverse=True)
    print(f"=== top {args.top} markets by 24h trading volume (USD) ===")
    print(f'{"24h vol":>12}  {"yes":>5}  {"chg1d":>6}  question')
    print("-" * 110)
    for m in active[: args.top]:
        yes = _yes_price(m)
        chg = m.get("oneDayPriceChange") or 0
        q = (m.get("question") or "")[:75]
        yes_s = f"{yes:.2f}" if yes is not None else "  -  "
        try:
            chg_f = float(chg)
        except (TypeError, ValueError):
            chg_f = 0.0
        print(f"{_v24(m):>12,.0f}  {yes_s:>5}  {chg_f:>+6.2f}  {q}")


if __name__ == "__main__":
    main()
