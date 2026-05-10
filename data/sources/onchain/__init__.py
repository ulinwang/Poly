"""Polygon on-chain ingest — v8 scaffold (NotImplementedError until
ABI files are dropped into abis/ and puller.py is fleshed out).

Public surface kept symmetric with the API ingest packages so
downstream code can `from data.sources import onchain` without
crashing on import.
"""
from .puller import main
from .schema import (
    ONCHAIN_ORDER_FILLED_DDL, ONCHAIN_ORDERS_MATCHED_DDL,
    ONCHAIN_SPLIT_DDL, ONCHAIN_MERGE_DDL, ONCHAIN_REDEEM_DDL,
    ensure_onchain_schemas,
)

__all__ = [
    "main",
    "ONCHAIN_ORDER_FILLED_DDL", "ONCHAIN_ORDERS_MATCHED_DDL",
    "ONCHAIN_SPLIT_DDL", "ONCHAIN_MERGE_DDL", "ONCHAIN_REDEEM_DDL",
    "ensure_onchain_schemas",
]
