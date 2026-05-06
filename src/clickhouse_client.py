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

    def reset_sim_schema(self) -> None:
        """Drop all sim-related tables. Useful when migrating between
        schema versions during development. Data is lost — only call when
        you have nothing important persisted."""
        for tbl in (
            "agent_simulations", "agent_personas", "agent_actions",
            "agent_fills", "agent_positions",
        ):
            self.client.execute(f"DROP TABLE IF EXISTS {self.database}.{tbl}")

    def ensure_sim_schema(self) -> None:
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.agent_simulations (
                sim_id String,
                market_id String,
                market_slug String,
                engine String,
                engine_param Float64,
                persona_set String,
                n_agents UInt32,
                n_ticks UInt32,
                started_at DateTime,
                ended_at Nullable(DateTime),
                final_sim_yes_price Float64,
                market_resolved_yes Nullable(UInt8),
                notes String
            )
            ENGINE = MergeTree
            ORDER BY (started_at, sim_id)
            SETTINGS index_granularity = 8192
            """
        )
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.agent_personas (
                sim_id String,
                agent_id UInt32,
                persona_type String,
                risk_aversion Float64,
                capital_initial Float64,
                profile_text String
            )
            ENGINE = MergeTree
            ORDER BY (sim_id, agent_id)
            SETTINGS index_granularity = 8192
            """
        )
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.agent_actions (
                sim_id String,
                tick UInt32,
                agent_id UInt32,
                order_type String,
                outcome String,
                side String,
                price Float64,
                size_usd Float64,
                yes_mid_before Float64,
                yes_mid_after Float64,
                shares_traded Float64,
                n_fills UInt32,
                reasoning String,
                raw_response String,
                api_latency_ms UInt32,
                api_error String,
                acted_at DateTime
            )
            ENGINE = MergeTree
            PARTITION BY toYYYYMM(acted_at)
            ORDER BY (sim_id, tick, agent_id)
            SETTINGS index_granularity = 8192
            """
        )
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.agent_fills (
                sim_id String,
                tick UInt32,
                maker_order_id UInt64,
                taker_order_id UInt64,
                maker_agent_id UInt32,
                taker_agent_id UInt32,
                outcome String,
                maker_side String,
                price Float64,
                size Float64,
                notional Float64,
                filled_at DateTime
            )
            ENGINE = MergeTree
            PARTITION BY toYYYYMM(filled_at)
            ORDER BY (sim_id, tick, maker_order_id, taker_order_id)
            SETTINGS index_granularity = 8192
            """
        )
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.agent_positions (
                sim_id String,
                tick UInt32,
                agent_id UInt32,
                yes_shares Float64,
                no_shares Float64,
                cash Float64,
                realized_pnl Float64,
                unrealized_pnl Float64
            )
            ENGINE = MergeTree
            ORDER BY (sim_id, tick, agent_id)
            SETTINGS index_granularity = 8192
            """
        )
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.market_trade_history (
                market_id String,
                token_id String,
                trade_time DateTime,
                side String,
                price Float64,
                size Float64,
                maker_address String,
                taker_address String,
                fetched_at DateTime
            )
            ENGINE = MergeTree
            PARTITION BY toYYYYMM(trade_time)
            ORDER BY (market_id, token_id, trade_time)
            SETTINGS index_granularity = 8192
            """
        )

    def insert_simulation(self, row: tuple) -> None:
        self.client.execute(
            f"""
            INSERT INTO {self.database}.agent_simulations (
                sim_id, market_id, market_slug, engine, engine_param,
                persona_set, n_agents, n_ticks, started_at, ended_at,
                final_sim_yes_price, market_resolved_yes, notes
            ) VALUES
            """,
            [row],
        )

    def insert_personas(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.agent_personas (
                sim_id, agent_id, persona_type, risk_aversion,
                capital_initial, profile_text
            ) VALUES
            """,
            rows,
        )

    def insert_actions(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.agent_actions (
                sim_id, tick, agent_id, order_type, outcome, side,
                price, size_usd, yes_mid_before, yes_mid_after,
                shares_traded, n_fills, reasoning, raw_response,
                api_latency_ms, api_error, acted_at
            ) VALUES
            """,
            rows,
        )

    def insert_fills(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.agent_fills (
                sim_id, tick, maker_order_id, taker_order_id,
                maker_agent_id, taker_agent_id, outcome, maker_side,
                price, size, notional, filled_at
            ) VALUES
            """,
            rows,
        )

    def insert_positions(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.agent_positions (
                sim_id, tick, agent_id, yes_shares, no_shares, cash,
                realized_pnl, unrealized_pnl
            ) VALUES
            """,
            rows,
        )

    def insert_trade_history(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.market_trade_history (
                market_id, token_id, trade_time, side, price, size,
                maker_address, taker_address, fetched_at
            ) VALUES
            """,
            rows,
        )

    def ensure_wallet_features_schema(self) -> None:
        """v4: empirical wallet calibration table.

        Each row is one wallet's pre-event behavioral fingerprint. The
        target_market_id pins the cutoff: only wallet activity strictly
        before that market opened is summarized here, so it is safe to
        feed into agent initialization without leaking the resolution.
        """
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.wallet_features (
                wallet_addr      String,
                target_market_id String,
                capital_usd      Float64,
                tx_count         UInt32,
                maker_ratio      Float64,
                avg_position_usd Float64,
                asset_diversity  UInt32,
                avg_holding_h    Float64,
                past_accuracy    Float64,
                n_resolved_prior UInt32,
                fetched_at       DateTime
            )
            ENGINE = ReplacingMergeTree(fetched_at)
            ORDER BY (target_market_id, wallet_addr)
            SETTINGS index_granularity = 8192
            """
        )

    def insert_wallet_features(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.wallet_features (
                wallet_addr, target_market_id, capital_usd, tx_count,
                maker_ratio, avg_position_usd, asset_diversity,
                avg_holding_h, past_accuracy, n_resolved_prior, fetched_at
            ) VALUES
            """,
            rows,
        )

    def fetch_wallet_features(self, target_market_id: str) -> list[tuple]:
        return self.client.execute(
            f"""
            SELECT wallet_addr, capital_usd, tx_count, maker_ratio,
                   avg_position_usd, asset_diversity, avg_holding_h,
                   past_accuracy, n_resolved_prior
            FROM {self.database}.wallet_features FINAL
            WHERE target_market_id = %(mid)s
            """,
            {"mid": str(target_market_id)},
        )

    def fetch_wallets_in_market(self, market_id: str) -> list[str]:
        """Distinct wallets that appeared on either side of any trade
        in market_trade_history for this market_id."""
        rows = self.client.execute(
            f"""
            SELECT DISTINCT addr FROM (
                SELECT maker_address AS addr
                FROM {self.database}.market_trade_history
                WHERE market_id = %(mid)s AND maker_address != ''
                UNION ALL
                SELECT taker_address AS addr
                FROM {self.database}.market_trade_history
                WHERE market_id = %(mid)s AND taker_address != ''
            )
            WHERE addr != ''
            """,
            {"mid": str(market_id)},
        )
        return [r[0] for r in rows]

    def ensure_serd_schema(self) -> None:
        """v4: per-(sim, method, role) ROI table for SERD validation."""
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.serd_results (
                sim_id     String,
                method     String,
                role       String,
                n_agents   UInt32,
                mean_roi   Float64,
                vol_share  Float64,
                fetched_at DateTime
            )
            ENGINE = ReplacingMergeTree(fetched_at)
            ORDER BY (sim_id, method, role)
            SETTINGS index_granularity = 8192
            """
        )

    def insert_serd_results(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.serd_results (
                sim_id, method, role, n_agents, mean_roi, vol_share, fetched_at
            ) VALUES
            """,
            rows,
        )

    def fetch_market_by_slug(self, slug: str) -> Optional[tuple]:
        rows = self.client.execute(
            f"""
            SELECT market_id, slug, question, description,
                   outcomes, clob_token_ids, outcome_prices,
                   volume, end_date, `closed`
            FROM {self.database}.markets FINAL
            WHERE slug = %(slug)s
            LIMIT 1
            """,
            {"slug": slug},
        )
        return rows[0] if rows else None

    def ensure_predictions_schema(self) -> None:
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.agent_predictions (
                prediction_id String,
                market_id String,
                model String,
                prompt_version String,
                yes_probability Float64,
                confidence String,
                reasoning String,
                raw_response String,
                prompt_tokens UInt32,
                completion_tokens UInt32,
                market_yes_price_at_prediction Float64,
                market_resolved_yes Nullable(UInt8),
                market_volume_at_prediction Float64,
                api_latency_ms UInt32,
                api_error String,
                predicted_at DateTime
            )
            ENGINE = MergeTree
            PARTITION BY toYYYYMM(predicted_at)
            ORDER BY (model, prompt_version, predicted_at, market_id)
            SETTINGS index_granularity = 8192
            """
        )

    def insert_predictions(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.agent_predictions (
                prediction_id, market_id, model, prompt_version,
                yes_probability, confidence, reasoning, raw_response,
                prompt_tokens, completion_tokens,
                market_yes_price_at_prediction, market_resolved_yes,
                market_volume_at_prediction,
                api_latency_ms, api_error, predicted_at
            ) VALUES
            """,
            rows,
        )

    def fetch_markets_for_prediction(
        self,
        limit: int,
        only_closed: bool = True,
        min_volume: float = 0.0,
        skip_predicted_by_model: Optional[str] = None,
        skip_predicted_by_prompt: Optional[str] = None,
    ) -> Sequence[tuple]:
        """Return up to `limit` rows of (market_id, slug, question,
        description, outcomes, outcome_prices, volume, end_date, closed).

        If `skip_predicted_by_model` is set, markets that already have a
        prediction for that (model, prompt_version) pair are excluded.
        """
        params: dict[str, object] = {
            "lim": int(limit),
            "min_vol": float(min_volume),
        }
        skip_clause = ""
        if skip_predicted_by_model:
            params["skip_model"] = skip_predicted_by_model
            params["skip_prompt"] = skip_predicted_by_prompt or ""
            skip_clause = f"""
                AND market_id NOT IN (
                    SELECT market_id FROM {self.database}.agent_predictions
                    WHERE model = %(skip_model)s
                      AND prompt_version = %(skip_prompt)s
                      AND api_error = ''
                )
            """
        closed_clause = "AND `closed` = 1" if only_closed else ""
        return self.client.execute(
            f"""
            SELECT market_id, slug, question, description,
                   outcomes, outcome_prices, volume, end_date, `closed`
            FROM {self.database}.markets FINAL
            WHERE volume >= %(min_vol)s
              {closed_clause}
              {skip_clause}
            ORDER BY volume DESC
            LIMIT %(lim)s
            """,
            params,
        )

    def ensure_markets_schema(self) -> None:
        self.client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.database}.markets (
                market_id String,
                slug String,
                question String,
                description String,
                category String,
                outcomes Array(String),
                clob_token_ids Array(String),
                outcome_prices Array(Float64),
                volume Float64,
                end_date Nullable(DateTime),
                active UInt8,
                closed UInt8,
                fetched_at DateTime
            )
            ENGINE = ReplacingMergeTree(fetched_at)
            ORDER BY market_id
            SETTINGS index_granularity = 8192
            """
        )

    def insert_markets(self, rows: Sequence[tuple]) -> None:
        if not rows:
            return
        self.client.execute(
            f"""
            INSERT INTO {self.database}.markets (
                market_id, slug, question, description, category,
                outcomes, clob_token_ids, outcome_prices, volume,
                end_date, active, closed, fetched_at
            ) VALUES
            """,
            rows,
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
