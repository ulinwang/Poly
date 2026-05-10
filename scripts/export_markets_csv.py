"""
Export the polymetl.markets table to a CSV file (deduplicated via FINAL).

Array columns (outcomes, clob_token_ids, outcome_prices) are serialized as
JSON strings so the CSV stays single-row-per-market and round-trips losslessly.

Usage:
    uv run python scripts/export_markets_csv.py
    uv run python scripts/export_markets_csv.py --out ~/Desktop/markets.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clickhouse_driver import Client


COLUMNS = [
    "market_id",
    "slug",
    "question",
    "description",
    "category",
    "outcomes",
    "clob_token_ids",
    "outcome_prices",
    "volume",
    "end_date",
    "active",
    "closed",
    "fetched_at",
]

ARRAY_COLUMNS = {"outcomes", "clob_token_ids", "outcome_prices"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(Path.home() / "Desktop" / "polymetl_markets.csv"),
        help="output CSV path (default: ~/Desktop/polymetl_markets.csv)",
    )
    parser.add_argument("--host", default=os.getenv("POLYMETL_CLICKHOUSE_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("POLYMETL_CLICKHOUSE_PORT", "9000")))
    parser.add_argument("--user", default=os.getenv("POLYMETL_CLICKHOUSE_USER", "default"))
    parser.add_argument("--password", default=os.getenv("POLYMETL_CLICKHOUSE_PASSWORD", ""))
    parser.add_argument("--database", default=os.getenv("POLYMETL_CLICKHOUSE_DATABASE", "polymetl"))
    parser.add_argument("--batch", type=int, default=10_000, help="rows per server-side fetch")
    args = parser.parse_args()

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    client = Client(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        settings={"max_block_size": args.batch},
    )

    total = client.execute("SELECT count() FROM markets FINAL")[0][0]
    print(f"exporting {total:,} unique markets to {out_path}")

    select_cols = ", ".join(COLUMNS)
    query = f"SELECT {select_cols} FROM markets FINAL ORDER BY fetched_at DESC, market_id"

    written = 0
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(COLUMNS)

        rows_iter = client.execute_iter(query)
        for row in rows_iter:
            out = []
            for col, val in zip(COLUMNS, row):
                if col in ARRAY_COLUMNS:
                    out.append(json.dumps(list(val), ensure_ascii=False))
                elif val is None:
                    out.append("")
                else:
                    out.append(val)
            writer.writerow(out)
            written += 1
            if written % 20_000 == 0:
                print(f"  ... {written:,} rows")

    size_mb = out_path.stat().st_size / 1_048_576
    print(f"done: {written:,} rows, {size_mb:.1f} MB -> {out_path}")


if __name__ == "__main__":
    main()
