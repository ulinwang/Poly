from __future__ import annotations

import argparse

from .clickhouse_client import ClickHouse
from .config import get_settings
from .etl import ETL


def main() -> None:
    parser = argparse.ArgumentParser(description="PolyMETL: ETL for Polymarket events")
    parser.add_argument("--start", type=int, default=None, help="Override start block (inclusive)")
    parser.add_argument("--end", type=int, default=None, help="Override end block (inclusive)")
    parser.add_argument(
        "--address",
        type=str,
        default=None,
        help="Exchange contract address to filter (overrides POLYMETL_EXCHANGE_ADDRESS)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if args.start is not None:
        settings.START_BLOCK = args.start
    if args.end is not None:
        settings.END_BLOCK = args.end
    if args.address:
        settings.EXCHANGE_ADDRESS = args.address

    ch = ClickHouse(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DATABASE,
    )
    etl = ETL(settings, ch)
    etl.run()


if __name__ == "__main__":
    main()
