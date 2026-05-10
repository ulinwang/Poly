"""High-level read-only query layer.

Every reader in agent/ and environment/ MUST import from here, never
from `data.store.clickhouse` directly. This indirection makes the
backing store swappable (e.g., to local parquet) and keeps SQL out
of the agent/environment business logic.

Modules:
    markets    — market metadata + slug→condition_id resolution
    trades     — per-trade rows + first-window VWAP
    orderbook  — book snapshots + bootstrap priors
    prices     — clob_prices_history reads
    holders    — top-holders + bios + display_names
    wallets    — per-wallet pre-event activity + resolution outcomes
    onchain    — onchain_* table queries (v8 scaffold; raises)
"""
