"""v8 — Polygon RPC ingest SCAFFOLD.

This file deliberately raises `NotImplementedError`. v8 ships only
the directory layout + ABI placeholders + DDL strings; the real
puller lands in v9 once the user provides a Polygon archive RPC
endpoint and the ABI files in `data/sources/onchain/abis/`.

Target tables (DDL in `schema.py`):
  - onchain_order_filled       (Polymarket Exchange OrderFilled)
  - onchain_orders_matched     (Polymarket Exchange OrdersMatched)
  - onchain_split              (ConditionalTokens PositionSplit)
  - onchain_merge              (ConditionalTokens PositionsMerge)
  - onchain_redeem             (ConditionalTokens PayoutRedemption)

Why scaffolded now: the v7 plan deliberately deferred on-chain
ingest because the API tables (gamma + clob + data-api) are
sufficient for the thesis run. The user's v8 module reorg requires
the directory exist for symmetry with the other three sources, so
we add it as a placeholder now.
"""
from __future__ import annotations

import argparse
import logging

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rpc-url", default=None,
        help="Polygon archive RPC endpoint (REQUIRED to run, but v8 is scaffold)",
    )
    parser.add_argument("--from-block", type=int, default=33_605_403,
                        help="Polymarket Exchange deployment block")
    parser.add_argument("--to-block", type=int, default=None)
    parser.add_argument("--contract", default="exchange",
                        choices=["exchange", "ctf", "all"])
    parser.parse_args()
    raise NotImplementedError(
        "data.sources.onchain.puller is a v8 scaffold. To enable: "
        "(1) drop ABI JSON files into data/sources/onchain/abis/, "
        "(2) implement event log subscription via web3.py "
        "(eth_getLogs in batches, decode with the ABI, write rows "
        "to ClickHouse using the DDLs in schema.py). "
        "Tracking issue: see docs/PAPER.md §future."
    )


if __name__ == "__main__":
    main()
