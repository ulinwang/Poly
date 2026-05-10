"""Polymarket Gamma API ingest (gamma-api.polymarket.com).

Full-fidelity ~125-field market metadata. Public re-exports below;
the renamed `gamma_full.py` lives at `puller.py` here.
"""
from .puller import (
    fetch_markets_page, iter_all_markets,
    ensure_markets_full_schema,
    market_to_full_row, insert_markets_full,
    run, main,
)

__all__ = [
    "fetch_markets_page", "iter_all_markets",
    "ensure_markets_full_schema",
    "market_to_full_row", "insert_markets_full",
    "run", "main",
]
