"""Polymarket data-api ingest (data-api.polymarket.com).

Public re-exports for the trades / holders / open-interest endpoints.
"""
from .puller import (
    DATA_API_BASE,
    ensure_dataapi_schemas,
    fetch_trades, fetch_holders, fetch_oi,
    crawl_endpoint, list_condition_ids,
    main,
)

__all__ = [
    "DATA_API_BASE",
    "ensure_dataapi_schemas",
    "fetch_trades", "fetch_holders", "fetch_oi",
    "crawl_endpoint", "list_condition_ids",
    "main",
]
