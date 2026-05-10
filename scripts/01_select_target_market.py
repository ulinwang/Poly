#!/usr/bin/env python3
"""Step 1 of 8 — Select a target market for the simulation.

v8 wraps `data.query.markets.select_resolved_markets`. Slated for
removal in v8 Stage 5 (replaced by experiments/configs/*.yaml).
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 1 of 8 — Select target market\n")
    import argparse
    from data.query.markets import select_resolved_markets

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-volume", type=float, default=5_000.0)
    parser.add_argument("--max-volume", type=float, default=5_000_000.0)
    parser.add_argument("--min-wallets", type=int, default=30)
    parser.add_argument("--end-after", default=None)
    parser.add_argument("--end-before", default=None)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    rows = select_resolved_markets(
        min_volume=args.min_volume, max_volume=args.max_volume,
        min_wallets=args.min_wallets,
        end_after_iso=args.end_after, end_before_iso=args.end_before,
        limit=args.limit,
    )
    if not rows:
        print("(no candidates)")
    else:
        print(f"{'slug':<70}  {'wallets':>7}  {'volume':>10}  end_date")
        print("-" * 110)
        for slug, _cid, vol, n_w, end, _q in rows:
            print(f"{slug[:68]:<70}  {n_w:>7}  {float(vol):>10.0f}  {end}")
        print(f"\nTop pick: --slug {rows[0][0]}")
