"""v8 — ClickHouse DDL for the on-chain tables. SCAFFOLD.

The DDL strings here are NOT yet executed by anything. Once
`puller.py` lands a real implementation in v9, an
`ensure_onchain_schemas(ch: ClickHouse)` helper here will run them.

Schema design notes:
  - All tables are `MergeTree` ORDER BY (block_number, log_index)
    so subsequent backfills are idempotent.
  - `tx_hash` + `log_index` together form the natural primary key.
  - Wallet addresses stored as lowercase hex Strings (keep
    consistent with `dataapi_trades.proxy_wallet`).
"""
from __future__ import annotations


ONCHAIN_ORDER_FILLED_DDL = """
CREATE TABLE IF NOT EXISTS polymetl.onchain_order_filled (
    block_number UInt64,
    block_time DateTime,
    tx_hash String,
    log_index UInt32,
    order_hash String,
    maker String,
    taker String,
    maker_asset_id String,
    taker_asset_id String,
    maker_amount_filled Decimal(38, 0),
    taker_amount_filled Decimal(38, 0),
    fee_recipient String,
    fee Decimal(38, 0),
    fetched_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (block_number, log_index)
"""

ONCHAIN_ORDERS_MATCHED_DDL = """
CREATE TABLE IF NOT EXISTS polymetl.onchain_orders_matched (
    block_number UInt64,
    block_time DateTime,
    tx_hash String,
    log_index UInt32,
    taker_order_hash String,
    taker String,
    maker_asset_id String,
    taker_asset_id String,
    maker_amount_filled Decimal(38, 0),
    taker_amount_filled Decimal(38, 0),
    fetched_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (block_number, log_index)
"""

ONCHAIN_SPLIT_DDL = """
CREATE TABLE IF NOT EXISTS polymetl.onchain_split (
    block_number UInt64,
    block_time DateTime,
    tx_hash String,
    log_index UInt32,
    stakeholder String,
    collateral_token String,
    parent_collection_id String,
    condition_id String,
    partition Array(UInt256),
    amount Decimal(38, 0),
    fetched_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (block_number, log_index)
"""

ONCHAIN_MERGE_DDL = """
CREATE TABLE IF NOT EXISTS polymetl.onchain_merge (
    block_number UInt64,
    block_time DateTime,
    tx_hash String,
    log_index UInt32,
    stakeholder String,
    collateral_token String,
    parent_collection_id String,
    condition_id String,
    partition Array(UInt256),
    amount Decimal(38, 0),
    fetched_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (block_number, log_index)
"""

ONCHAIN_REDEEM_DDL = """
CREATE TABLE IF NOT EXISTS polymetl.onchain_redeem (
    block_number UInt64,
    block_time DateTime,
    tx_hash String,
    log_index UInt32,
    redeemer String,
    collateral_token String,
    parent_collection_id String,
    condition_id String,
    index_sets Array(UInt256),
    payout Decimal(38, 0),
    fetched_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (block_number, log_index)
"""

ALL_DDLS = (
    ONCHAIN_ORDER_FILLED_DDL,
    ONCHAIN_ORDERS_MATCHED_DDL,
    ONCHAIN_SPLIT_DDL,
    ONCHAIN_MERGE_DDL,
    ONCHAIN_REDEEM_DDL,
)


def ensure_onchain_schemas(ch) -> None:
    """v8 scaffold — does nothing. Will execute DDLs in v9."""
    raise NotImplementedError(
        "ensure_onchain_schemas is a v8 scaffold; activate when "
        "data.sources.onchain.puller is implemented."
    )
