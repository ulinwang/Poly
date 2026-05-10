"""
Inspect every field the Polymarket Gamma API returns for a single market.

Usage:
    uv run python scripts/inspect_market_fields.py
    uv run python scripts/inspect_market_fields.py --slug will-trump-win-2024

This script does not touch ClickHouse; it just hits the public Gamma
API and pretty-prints the response, grouped by purpose. Used during
schema design to decide which fields to ingest.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Iterable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.sources.gamma_api import fetch_markets_page  # noqa: E402


GROUPS: dict[str, list[str]] = {
    "Identity": [
        "id", "slug", "question", "description", "conditionId",
        "marketMakerAddress", "tags",
    ],
    "Media": ["icon", "image", "twitter", "seriesColor"],
    "Outcomes / resolution": [
        "outcomes", "clobTokenIds", "outcomePrices",
        "umaResolutionStatus", "umaResolutionStatuses",
        "resolvedBy", "resolutionSource",
    ],
    "Order book / pricing": [
        "lastTradePrice", "bestBid", "bestAsk", "spread",
        "rewardsMinSize", "rewardsMaxSpread",
    ],
    "Volume (windowed)": [
        "volume", "volumeClob",
        "volume24hr", "volume1wk", "volume1mo", "volume1yr",
        "volume24hrClob", "volume1wkClob", "volume1moClob", "volume1yrClob",
    ],
    "Liquidity": ["liquidity", "liquidityClob", "liquidityNum"],
    "Price changes": [
        "oneHourPriceChange", "oneDayPriceChange",
        "oneWeekPriceChange", "oneMonthPriceChange", "oneYearPriceChange",
    ],
    "Timestamps": [
        "startDate", "endDate", "endDateIso", "closedTime",
        "createdAt", "updatedAt",
        "acceptingOrdersTimestamp", "deployingTimestamp",
    ],
    "Status flags": [
        "active", "closed", "archived", "restricted",
        "enableOrderBook", "acceptingOrders", "funded", "approved",
        "ready", "deploying", "automaticallyActive", "pendingDeployment",
    ],
    "Fees": [
        "makerBaseFee", "takerBaseFee", "feeSchedule",
        "feesEnabled", "feeType",
    ],
    "UMA / arbitration": [
        "umaBond", "umaReward", "customLiveness",
        "negRisk", "negRiskRequestID", "negRiskOther",
    ],
    "Stats / discovery": [
        "competitive", "holdingRewardsEnabled", "rfqEnabled",
    ],
    "Parent event grouping": [
        "events", "groupItemTitle", "groupItemThreshold",
        "seriesSlug", "clobRewards",
    ],
}


def _truncate(value: Any, width: int = 80) -> str:
    s = str(value)
    return s if len(s) <= width else s[: width - 3] + "..."


def _print_group(title: str, fields: Iterable[str], market: dict, seen: set[str]) -> None:
    rows = [(k, market.get(k)) for k in fields if k in market]
    if not rows:
        return
    print(title)
    for k, v in rows:
        print(f"  {k:30s} = {_truncate(v)}")
        seen.add(k)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slug", help="Specific market slug to fetch. Defaults to the first market."
    )
    args = parser.parse_args()

    if args.slug:
        # Gamma supports filtering by slug via a separate endpoint; for
        # simplicity we just scan the first page and match.
        page = fetch_markets_page(limit=500, offset=0)
        market = next((m for m in page if m.get("slug") == args.slug), None)
        if market is None:
            raise SystemExit(f"slug {args.slug!r} not in first page; try without --slug")
    else:
        market = fetch_markets_page(limit=1, offset=0)[0]

    print(f"Inspecting market: id={market.get('id')} slug={market.get('slug')!r}")
    print(f"Total fields returned: {len(market)}")
    print()

    seen: set[str] = set()
    for title, fields in GROUPS.items():
        _print_group(f"=== {title} ===", fields, market, seen)

    rest = sorted(set(market) - seen)
    if rest:
        print("=== Other / uncategorized ===")
        for k in rest:
            print(f"  {k:30s} = {_truncate(market[k])}")


if __name__ == "__main__":
    main()
