"""
Export polymetl.markets_full (146k rows × 128 columns) to a single CSV.

Array columns (outcomes, clob_token_ids, outcome_prices, uma_resolution_statuses)
are serialized as JSON strings to round-trip losslessly.
JSON-blob string columns (events_json, clob_rewards_json, tags_json,
fee_schedule_json, raw_json) are written through as-is.

Usage:
    uv run python scripts/export_markets_full_csv.py
    uv run python scripts/export_markets_full_csv.py --no-raw           # skip raw_json column to keep file small
    uv run python scripts/export_markets_full_csv.py --out ~/Desktop/foo.csv

Heads-up: with raw_json the file is ~1 GB. With --no-raw it's ~150 MB.
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
from src.gamma_full import FIELDS, EXTRA_COLS


ARRAY_COLS = {"outcomes", "clob_token_ids", "outcome_prices", "uma_resolution_statuses"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(Path.home() / "Desktop" / "polymetl_markets_full.csv"),
    )
    parser.add_argument("--no-raw", action="store_true",
                        help="Drop raw_json column to keep the CSV small.")
    parser.add_argument("--host",     default=os.getenv("POLYMETL_CLICKHOUSE_HOST", "localhost"))
    parser.add_argument("--port",     type=int, default=int(os.getenv("POLYMETL_CLICKHOUSE_PORT", "9000")))
    parser.add_argument("--user",     default=os.getenv("POLYMETL_CLICKHOUSE_USER", "default"))
    parser.add_argument("--password", default=os.getenv("POLYMETL_CLICKHOUSE_PASSWORD", ""))
    parser.add_argument("--database", default=os.getenv("POLYMETL_CLICKHOUSE_DATABASE", "polymetl"))
    parser.add_argument("--batch",    type=int, default=10_000)
    args = parser.parse_args()

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    columns = [name for name, _src, _ctype, _kind in FIELDS] + [name for name, _ in EXTRA_COLS]
    if args.no_raw and "raw_json" in columns:
        columns = [c for c in columns if c != "raw_json"]

    client = Client(
        host=args.host, port=args.port, user=args.user,
        password=args.password, database=args.database,
        settings={"max_block_size": args.batch},
    )

    total = client.execute("SELECT count() FROM markets_full FINAL")[0][0]
    print(f"exporting {total:,} rows × {len(columns)} cols  →  {out_path}")
    if "raw_json" in columns:
        print("note: raw_json included; expect ~1 GB output. Use --no-raw to skip it (~150 MB).")

    select_cols = ", ".join(columns)
    query = f"SELECT {select_cols} FROM markets_full FINAL ORDER BY fetched_at DESC, market_id"

    written = 0
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(columns)
        for row in client.execute_iter(query):
            out = []
            for col, val in zip(columns, row):
                if col in ARRAY_COLS:
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
    print(f"done: {written:,} rows, {size_mb:.1f} MB → {out_path}")


if __name__ == "__main__":
    main()
