from __future__ import annotations

import datetime as dt
from typing import Iterable, Optional, Sequence

from clickhouse_driver import Client


class ClickHouse:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
    ) -> None:
        self.database = database
        # Connect without specifying database first, to allow creating it
        self.client = Client(
            host=host,
            port=port,
            user=user,
            password=password,
            settings={"max_query_size": 10_000_000},
        )
        # Ensure database exists, then switch
        self.client.execute(f"CREATE DATABASE IF NOT EXISTS {database}")
        self.client.execute(f"USE {database}")

    def ensure_schema(self) -> None:
        # Events tables
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.order_filled (
                chain_id UInt32,
                block_number UInt32,
                block_time DateTime,
                tx_hash String,
                log_index UInt32,
                contract_address String,
                order_hash String,
                maker String,
                taker String,
                maker_asset_id String,
                taker_asset_id String,
                maker_amount_filled String,
                taker_amount_filled String,
                fee String
            )
            ENGINE = ReplacingMergeTree
            PARTITION BY toYYYYMM(block_time)
            ORDER BY (chain_id, block_number, tx_hash, log_index)
            SETTINGS index_granularity = 8192
            """
        )

        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.orders_matched (
                chain_id UInt32,
                block_number UInt32,
                block_time DateTime,
                tx_hash String,
                log_index UInt32,
                contract_address String,
                taker_order_hash String,
                taker_order_maker String,
                maker_asset_id String,
                taker_asset_id String,
                maker_amount_filled String,
                taker_amount_filled String
            )
            ENGINE = ReplacingMergeTree
            PARTITION BY toYYYYMM(block_time)
            ORDER BY (chain_id, block_number, tx_hash, log_index)
            SETTINGS index_granularity = 8192
            """
        )

        # Raw storage for other events (unparsed)
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.other_events (
                chain_id UInt32,
                block_number UInt32,
                block_time DateTime,
                tx_hash String,
                log_index UInt32,
                contract_address String,
                topic0 String,
                topics Array(String),
                data String
            )
            ENGINE = ReplacingMergeTree
            PARTITION BY toYYYYMM(block_time)
            ORDER BY (chain_id, block_number, tx_hash, log_index)
            SETTINGS index_granularity = 8192
            """
        )

        # Progress table
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.etl_progress (
                chain_id UInt32,
                exchange_address String,
                last_block UInt32,
                updated_at DateTime
            )
            ENGINE = ReplacingMergeTree
            ORDER BY (chain_id, exchange_address, updated_at)
            SETTINGS index_granularity = 8192
            """
        )

    def insert_order_filled(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.order_filled (
                chain_id, block_number, block_time, tx_hash, log_index, contract_address,
                order_hash, maker, taker, maker_asset_id, taker_asset_id,
                maker_amount_filled, taker_amount_filled, fee
            ) VALUES
            """,
            rows,
        )

    def insert_orders_matched(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.orders_matched (
                chain_id, block_number, block_time, tx_hash, log_index, contract_address,
                taker_order_hash, taker_order_maker, maker_asset_id, taker_asset_id,
                maker_amount_filled, taker_amount_filled
            ) VALUES
            """,
            rows,
        )

    def insert_other_events(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.other_events (
                chain_id, block_number, block_time, tx_hash, log_index, contract_address,
                topic0, topics, data
            ) VALUES
            """,
            rows,
        )

    def get_last_block(self, chain_id: int, exchange_address: Optional[str]) -> Optional[int]:
        # If exchange_address is provided, first try specific progress; if not found, fall back to global (no address filter)
        params: dict[str, object] = {"chain_id": int(chain_id)}
        if exchange_address:
            rows = self.client.execute(
                f"""
                SELECT max(last_block) FROM {self.database}.etl_progress
                WHERE chain_id = %(chain_id)s AND exchange_address = %(addr)s
                """,
                {**params, "addr": str(exchange_address.lower())},
            )
            val = rows[0][0] if rows else None
            if val is not None:
                return int(val)
        # Fallback: ignore address filter and use global max for this chain
        rows = self.client.execute(
            f"""
            SELECT max(last_block) FROM {self.database}.etl_progress
            WHERE chain_id = %(chain_id)s
            """,
            params,
        )
        val = rows[0][0] if rows else None
        return int(val) if val is not None else None

    def update_progress(self, chain_id: int, exchange_address: Optional[str], last_block: int) -> None:
        # Write specific address progress (if provided) AND a global progress row (empty address)
        now = dt.datetime.utcnow()
        rows = [
            (chain_id, (exchange_address or "").lower(), int(last_block), now),
        ]
        if exchange_address:
            # Ensure a global row exists/advances too for easy resume without address filter
            rows.append((chain_id, "", int(last_block), now))
        self.client.execute(
            f"""
            INSERT INTO {self.database}.etl_progress (
                chain_id, exchange_address, last_block, updated_at
            ) VALUES
        """,
            rows,
        )
