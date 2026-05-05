from __future__ import annotations

import datetime as dt
import random
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from web3 import Web3
from web3.types import FilterParams, LogReceipt
from web3.middleware import geth_poa_middleware

from .clickhouse_client import ClickHouse
from .config import Settings
from .events import (
    TOPIC_ORDER_FILLED,
    TOPIC_ORDERS_MATCHED,
    decode_order_filled,
    decode_orders_matched,
)


class ETL:
    def __init__(self, settings: Settings, ch: ClickHouse) -> None:
        self.settings = settings
        self.ch = ch
        self.web3 = Web3(Web3.HTTPProvider(settings.RPC_URL, request_kwargs={"timeout": 30}))
        # Polygon is a PoA-like chain; inject POA middleware to handle extraData field size
        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    def _parse_retry_after_seconds(self, msg: str) -> Optional[int]:
        """Parse messages like 'retry in 10m0s' or 'retry in 30s' to seconds."""
        m = re.search(r"retry in (?:(\d+)m)?(\d+)s", msg, flags=re.IGNORECASE)
        if not m:
            return None
        minutes = int(m.group(1)) if m.group(1) else 0
        seconds = int(m.group(2)) if m.group(2) else 0
        return minutes * 60 + seconds

    def _get_block_timestamp(self, block_number: int) -> int:
        backoff = 30  # seconds; exponential when provider doesn't specify
        while True:
            try:
                block = self.web3.eth.get_block(block_number)
                return int(block["timestamp"])  # type: ignore[index]
            except ValueError as e:
                msg = str(e)
                if "Too many requests" in msg or "-32090" in msg or "rate limit" in msg.lower():
                    suggested = self._parse_retry_after_seconds(msg)
                    sleep_for = suggested if suggested is not None else min(600, backoff)
                    jitter = random.randint(0, max(1, min(30, sleep_for // 10)))
                    total_sleep = sleep_for + jitter
                    print(
                        f"[rate-limit:block] {msg}; sleeping {total_sleep}s before retrying block {block_number}"
                    )
                    time.sleep(total_sleep)
                    if suggested is None:
                        backoff = min(600, backoff * 2)
                    else:
                        backoff = 30
                    continue
                else:
                    raise

    def _get_logs(self, start: int, end: int) -> List[LogReceipt]:
        # When an exchange address is provided, fetch all events for that address (no topic filter)
        # so we also collect other events without parsing them. If no address is provided, restrict
        # by topics to avoid scanning the entire chain.
        params: FilterParams = {
            "fromBlock": start,
            "toBlock": end,
        }
        if self.settings.EXCHANGE_ADDRESS:
            params["address"] = Web3.to_checksum_address(self.settings.EXCHANGE_ADDRESS)
        else:
            params["topics"] = [[TOPIC_ORDER_FILLED, TOPIC_ORDERS_MATCHED]]
        logs = self.web3.eth.get_logs(params)
        return list(logs)

    def _decode_and_stage(self, logs: List[LogReceipt]) -> Tuple[List[tuple], List[tuple], List[tuple]]:
        filled_rows: List[tuple] = []
        matched_rows: List[tuple] = []
        other_rows: List[tuple] = []
        ts_cache: dict[int, dt.datetime] = {}
        decode_errors = 0
        for log in logs:
            block_number = int(log["blockNumber"])  # type: ignore[index]
            tx_hash = Web3.to_hex(log["transactionHash"])  # type: ignore[index]
            log_index = int(log["logIndex"])  # type: ignore[index]
            # Normalize address/topic types (HexBytes -> hex string)
            try:
                contract_address = Web3.to_checksum_address(
                    Web3.to_hex(log["address"])  # type: ignore[index]
                ).lower()
            except Exception:
                # Fallback if already a string
                contract_address = str(log["address"]).lower()  # type: ignore[index]
            topics_list = log["topics"]  # type: ignore[index]
            topic0 = Web3.to_hex(topics_list[0]).lower() if topics_list else ""
            ts = ts_cache.get(block_number)
            if ts is None:
                ts = dt.datetime.utcfromtimestamp(self._get_block_timestamp(block_number))
                ts_cache[block_number] = ts

            if topic0 == TOPIC_ORDER_FILLED:
                try:
                    (order_hash, maker, taker, maker_asset_id, taker_asset_id, maker_amount_filled, taker_amount_filled, fee) = (
                        decode_order_filled(self.web3, log)
                    )
                except Exception as e:
                    decode_errors += 1
                    print(f"[decode-error] OrderFilled logIndex={log_index} tx={tx_hash}: {e}")
                    continue
                filled_rows.append(
                    (
                        int(self.settings.CHAIN_ID),
                        block_number,
                        ts,
                        tx_hash,
                        log_index,
                        contract_address,
                        order_hash,
                        maker,
                        taker,
                        maker_asset_id,
                        taker_asset_id,
                        maker_amount_filled,
                        taker_amount_filled,
                        fee,
                    )
                )
            elif topic0 == TOPIC_ORDERS_MATCHED:
                try:
                    (taker_order_hash, taker_order_maker, maker_asset_id, taker_asset_id, maker_amount_filled, taker_amount_filled) = (
                        decode_orders_matched(self.web3, log)
                    )
                except Exception as e:
                    decode_errors += 1
                    print(f"[decode-error] OrdersMatched logIndex={log_index} tx={tx_hash}: {e}")
                    continue
                matched_rows.append(
                    (
                        int(self.settings.CHAIN_ID),
                        block_number,
                        ts,
                        tx_hash,
                        log_index,
                        contract_address,
                        taker_order_hash,
                        taker_order_maker,
                        maker_asset_id,
                        taker_asset_id,
                        maker_amount_filled,
                        taker_amount_filled,
                    )
                )
            else:
                # Persist other events as raw records
                try:
                    topics_strs = [Web3.to_hex(t).lower() for t in topics_list] if topics_list else []
                except Exception:
                    # If already strings
                    topics_strs = [str(t).lower() for t in topics_list] if topics_list else []
                try:
                    data_hex = Web3.to_hex(log["data"])  # type: ignore[index]
                except Exception:
                    data_hex = str(log["data"])  # type: ignore[index]
                other_rows.append(
                    (
                        int(self.settings.CHAIN_ID),
                        block_number,
                        ts,
                        tx_hash,
                        log_index,
                        contract_address,
                        topic0,
                        topics_strs,
                        data_hex,
                    )
                )
        if decode_errors:
            print(f"[decode] errors={decode_errors} on this batch")
        return filled_rows, matched_rows, other_rows

    def run(self) -> None:
        self.ch.ensure_schema()

        latest = int(self.web3.eth.block_number)
        last = self.ch.get_last_block(self.settings.CHAIN_ID, self.settings.EXCHANGE_ADDRESS)
        start_source = "cli" if self.settings.START_BLOCK is not None else ("progress" if last is not None else "latest-10000")
        start = (
            int(self.settings.START_BLOCK)
            if self.settings.START_BLOCK is not None
            else (last + 1 if last is not None else max(0, latest - 10_000))
        )
        end_target = int(self.settings.END_BLOCK) if self.settings.END_BLOCK is not None else latest

        # Adaptive batching: shrink on RPC -32062 (block range too large), grow slowly on success
        current_batch = max(1, int(self.settings.LOG_BATCH_SIZE))
        max_batch = max(1, int(self.settings.LOG_BATCH_SIZE))
        rate_backoff = 30  # seconds, exponential backoff on rate limit when provider doesn't specify

        # Progress counters
        total_blocks = max(0, end_target - start + 1)
        processed_blocks = 0
        total_logs = 0
        total_filled = 0
        total_matched = 0
        total_other = 0
        t0 = time.time()

        print(
            (
                f"[start] chain={self.settings.CHAIN_ID} address={str(self.settings.EXCHANGE_ADDRESS or '').lower()} "
                f"range=[{start}, {end_target}] blocks={total_blocks} initial_batch={current_batch} rpc={self.settings.RPC_URL} "
                f"(from {start_source})"
            )
        )

        current = start
        while current <= end_target:
            # Determine tentative upper bound for this iteration
            to_block = min(current + current_batch - 1, end_target)

            try:
                logs = self._get_logs(current, to_block)
            except ValueError as e:  # web3 raises ValueError with RPC error body
                # Detect Polygon RPC "Block range is too large"
                msg = str(e)
                if "Block range is too large" in msg or "-32062" in msg:
                    # halve the batch and retry this iteration
                    if current_batch == 1:
                        # cannot shrink further; re-raise
                        raise
                    new_batch = max(1, current_batch // 2)
                    print(
                        f"[shrink] range-too-large from batch {current_batch} -> {new_batch} for range {current}-{to_block}"
                    )
                    current_batch = new_batch
                    continue
                elif "Too many requests" in msg or "-32090" in msg or "rate limit" in msg.lower():
                    # Provider rate limit: sleep for suggested duration or backoff, then retry same range
                    suggested = self._parse_retry_after_seconds(msg)
                    sleep_for = suggested if suggested is not None else min(600, rate_backoff)
                    # Add small jitter to avoid thundering herd
                    jitter = random.randint(0, max(1, min(30, sleep_for // 10)))
                    total_sleep = sleep_for + jitter
                    # Slightly reduce current batch to be nicer to provider
                    current_batch = max(1, (current_batch * 4) // 5)  # -20%
                    print(
                        f"[rate-limit] {msg}; sleeping {total_sleep}s before retrying range {current}-{to_block} with batch {current_batch}"
                    )
                    time.sleep(total_sleep)
                    if suggested is None:
                        rate_backoff = min(600, rate_backoff * 2)
                    else:
                        rate_backoff = 30  # reset to default after honoring suggested wait
                    continue
                else:
                    # unknown ValueError; re-raise
                    raise

            # Success; decode and insert
            if not logs:
                # No logs in this range; still update progress and print
                filled_rows, matched_rows, other_rows = ([], [], [])
            else:
                filled_rows, matched_rows, other_rows = self._decode_and_stage(logs)
            if filled_rows:
                self.ch.insert_order_filled(filled_rows)
            if matched_rows:
                self.ch.insert_orders_matched(matched_rows)
            if other_rows:
                self.ch.insert_other_events(other_rows)

            # Update progress at the end of each successful subrange
            self.ch.update_progress(self.settings.CHAIN_ID, self.settings.EXCHANGE_ADDRESS, to_block)

            # Update progress metrics and output per-chunk stats
            iter_blocks = to_block - current + 1
            processed_blocks += iter_blocks
            n_logs = len(logs)
            n_filled = len(filled_rows)
            n_matched = len(matched_rows)
            n_other = len(other_rows)
            total_logs += n_logs
            total_filled += n_filled
            total_matched += n_matched
            total_other += n_other

            pct = (processed_blocks / total_blocks * 100.0) if total_blocks > 0 else 100.0
            elapsed = time.time() - t0
            rate = processed_blocks / elapsed if elapsed > 0 else 0.0
            print(
                (
                    f"[progress] {processed_blocks}/{total_blocks} blocks ({pct:.1f}%), "
                    f"range {current}-{to_block}, logs={n_logs}, filled={n_filled}, matched={n_matched}, other={n_other}, "
                    f"batch={current_batch}, speed={rate:.1f} blk/s"
                )
            )

            # Advance window
            current = to_block + 1

            # Attempt to slowly grow the batch back up (until max_batch)
            if current_batch < max_batch:
                # grow by 20%, at least +1
                grow = max(1, current_batch // 5)
                current_batch = min(max_batch, current_batch + grow)
            # Reset rate limit backoff on success
            rate_backoff = 30

        # Done
        elapsed = time.time() - t0
        print(
            (
                f"[done] blocks={processed_blocks}/{total_blocks}, logs={total_logs}, "
                f"filled={total_filled}, matched={total_matched}, other={total_other}, elapsed={elapsed:.1f}s"
            )
        )
