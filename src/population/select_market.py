"""v7 — Step 1: pick a target market for the simulation.

Queries `markets_resolved` (the resolved-only view over markets_full)
plus `dataapi_trades` for activity, returning candidates that satisfy
operator-specified criteria. The default criteria match the v4 paper
choice (a single-event binary YES/NO market with at least dozens of
unique wallet participants).

The returned slug is what every later script accepts as `--slug`.

Usage:
    uv run python -m src.population.select_market \\
        --min-volume 5000 --max-volume 500000 --min-wallets 30
"""
from __future__ import annotations

import argparse
import logging
from typing import Optional

from ..pipeline.clickhouse import ClickHouse
from ..pipeline.config import get_settings

log = logging.getLogger(__name__)


def list_candidates(
    ch: ClickHouse,
    min_volume: float = 5_000.0,
    max_volume: float = 5_000_000.0,
    min_wallets: int = 30,
    end_after_iso: Optional[str] = None,
    end_before_iso: Optional[str] = None,
    limit: int = 50,
    require_binary: bool = True,
) -> list[tuple]:
    """Return up to `limit` candidate markets matching the criteria.

    Each row: (slug, condition_id, volume, n_wallets, end_date, question)
    """
    where = [
        "mf.volume_num >= %(vmin)s",
        "mf.volume_num <= %(vmax)s",
    ]
    params: dict = {"vmin": min_volume, "vmax": max_volume,
                    "limit": int(limit), "min_wallets": int(min_wallets)}
    if end_after_iso:
        where.append("mr.end_date >= toDateTime(%(end_after)s)")
        params["end_after"] = end_after_iso
    if end_before_iso:
        where.append("mr.end_date <= toDateTime(%(end_before)s)")
        params["end_before"] = end_before_iso
    if require_binary:
        where.append("length(mr.outcomes) = 2")
    where_sql = " AND ".join(where)

    # markets_resolved is a view; join with markets_full for volume.
    sql = f"""
    SELECT mr.slug, mr.condition_id, mf.volume_num,
           uniqExact(t.proxy_wallet) AS n_wallets,
           mr.end_date, mr.question
    FROM polymetl.markets_resolved mr
    INNER JOIN polymetl.markets_full mf USING (condition_id)
    INNER JOIN polymetl.dataapi_trades t
        ON t.condition_id = mr.condition_id
    WHERE {where_sql}
    GROUP BY mr.slug, mr.condition_id, mf.volume_num, mr.end_date, mr.question
    HAVING n_wallets >= %(min_wallets)s
    ORDER BY n_wallets DESC, mf.volume_num DESC
    LIMIT %(limit)s
    """
    return ch.client.execute(sql, params)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-volume", type=float, default=5_000.0)
    parser.add_argument("--max-volume", type=float, default=5_000_000.0)
    parser.add_argument("--min-wallets", type=int, default=30)
    parser.add_argument("--end-after", default=None,
                        help="ISO date — only markets ending after this")
    parser.add_argument("--end-before", default=None,
                        help="ISO date — only markets ending before this")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--non-binary", action="store_true",
                        help="allow N-outcome markets (default: binary only)")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    s = get_settings()
    ch = ClickHouse(host=s.CLICKHOUSE_HOST, port=s.CLICKHOUSE_PORT,
                    user=s.CLICKHOUSE_USER, password=s.CLICKHOUSE_PASSWORD,
                    database=s.CLICKHOUSE_DATABASE)

    rows = list_candidates(
        ch,
        min_volume=args.min_volume, max_volume=args.max_volume,
        min_wallets=args.min_wallets,
        end_after_iso=args.end_after, end_before_iso=args.end_before,
        limit=args.limit, require_binary=not args.non_binary,
    )
    if not rows:
        log.warning("no candidates match criteria")
        return
    print(f"{'slug':<70}  {'wallets':>7}  {'volume':>10}  end_date")
    print("-" * 110)
    for slug, cid, vol, n_w, end, q in rows:
        print(f"{slug[:68]:<70}  {n_w:>7}  {float(vol):>10.0f}  {end}")
    print(f"\nTop pick: --slug {rows[0][0]}")


if __name__ == "__main__":
    main()
