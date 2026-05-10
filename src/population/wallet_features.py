"""v7 — Wallet feature extraction, SQL-only.

Replaces v4-v6's `wallet_calibration.py`, which fetched trade history
and closed-positions from the live data-api per wallet (slow, brittle,
required IP unblocking). Now everything comes from local ClickHouse:

  * `dataapi_trades`     — per-wallet trade-level history
  * `markets_resolved`   — resolution outcome per market
  * `clob_markets`       — slug → condition_id, token_ids
  * `dataapi_holders`    — bio + display_name per wallet (consumed
                            downstream by persona_generator.py)

Public API:
    calibrate(slug, dry_run=False) -> int          # rows inserted
    compute_features(trades, resolved_lookup) -> dict

Why SQL-only? The user added 42 M `dataapi_trades` rows + 110 k
resolved markets in v7 (see plan §"ClickHouse now contains").
Re-querying live API for data we already have on disk would violate
the v7 reproducibility commitment — every prior should be a
deterministic function of CH state.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import statistics
from typing import Optional

from data.store.clickhouse import ClickHouse
from data.store.config import get_settings
from .derive_priors import fetch_market_meta, market_open_ts

log = logging.getLogger(__name__)


def fetch_pre_event_trades(
    ch: ClickHouse, wallet: str, cutoff_ts: int,
) -> list[tuple]:
    """All this wallet's trades strictly before cutoff_ts.

    Returns rows of: (condition_id, outcome_index, price, size, trade_time)
    """
    return ch.client.execute(
        f"""
        SELECT condition_id, outcome_index, price, size, trade_time
        FROM polymetl.dataapi_trades
        WHERE proxy_wallet = %(w)s
          AND toUnixTimestamp(trade_time) < %(c)s
        """,
        {"w": wallet, "c": cutoff_ts},
    )


def fetch_resolved_lookup(
    ch: ClickHouse, condition_ids: list[str],
) -> dict[str, int]:
    """For each condition_id, return its winning_idx (0=Yes, 1=No,
    -1=unresolved/missing). Single batched SQL call."""
    if not condition_ids:
        return {}
    rows = ch.client.execute(
        f"""
        SELECT condition_id, winning_idx
        FROM polymetl.markets_resolved FINAL
        WHERE condition_id IN %(ids)s
        """,
        {"ids": tuple(condition_ids)},
    )
    return {cid: int(idx) for cid, idx in rows}


def compute_features(
    trades: list[tuple], resolved_lookup: dict[str, int],
) -> dict:
    """Aggregate one wallet's pre-event activity.

    `trades` rows: (condition_id, outcome_index, price, size, trade_time)
    `resolved_lookup`: condition_id → winning_idx (0/1/-1)

    See docs/EMPIRICAL_PRIORS.md for the source SQL of every field.
    Honest-feature note (carried from v4 audit): `maker_ratio` and
    `avg_holding_h` cannot be inferred from `dataapi_trades` alone —
    we keep them as 0.0 placeholders for schema parity, NOT consumed
    by `initialization.py` or persona_generator.py.
    """
    tx_count = len(trades)
    if tx_count == 0:
        return {
            "capital_usd": 0.0, "tx_count": 0, "maker_ratio": 0.0,
            "avg_position_usd": 0.0, "asset_diversity": 0,
            "avg_holding_h": 0.0, "past_accuracy": 0.0,
            "n_resolved_prior": 0,
        }

    notionals = [float(p) * float(s) for _, _, p, s, _ in trades]
    capital_usd = sum(notionals)
    avg_position_usd = statistics.fmean(notionals)
    asset_diversity = len({cid for cid, _, _, _, _ in trades})

    # Past accuracy = capital-weighted fraction of CLOSED positions
    # this wallet was on the winning side of. We aggregate per
    # (condition_id, outcome_index): the wallet's NET capital on each
    # side, then check whether that side won.
    by_side: dict[tuple[str, int], float] = {}
    for cid, oidx, p, s, _ in trades:
        key = (cid, int(oidx))
        by_side[key] = by_side.get(key, 0.0) + float(p) * float(s)

    win_capital = 0.0
    total_capital_resolved = 0.0
    resolved_cids: set[str] = set()
    for (cid, oidx), cap in by_side.items():
        win_idx = resolved_lookup.get(cid, -1)
        if win_idx == -1:
            continue
        resolved_cids.add(cid)
        total_capital_resolved += cap
        if oidx == win_idx:
            win_capital += cap

    n_resolved_prior = len(resolved_cids)
    past_accuracy = (
        win_capital / total_capital_resolved
        if total_capital_resolved > 0 else 0.0
    )

    return {
        "capital_usd": capital_usd,
        "tx_count": tx_count,
        "maker_ratio": 0.0,         # placeholder — see docstring
        "avg_position_usd": avg_position_usd,
        "asset_diversity": asset_diversity,
        "avg_holding_h": 0.0,       # placeholder — see docstring
        "past_accuracy": past_accuracy,
        "n_resolved_prior": n_resolved_prior,
    }


def calibrate(slug: str, dry_run: bool = False) -> int:
    """Build wallet_features rows for every wallet that traded the
    target market BEFORE its open. All from ClickHouse — no network.

    Returns the number of rows inserted.
    """
    settings = get_settings()
    ch = ClickHouse(
        host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
        user=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DATABASE,
    )
    ch.ensure_sim_schema()
    ch.ensure_wallet_features_schema()

    meta = fetch_market_meta(ch, slug)
    cutoff_ts = market_open_ts(ch, meta["condition_id"])
    cutoff_iso = dt.datetime.utcfromtimestamp(cutoff_ts).isoformat()
    log.info("calibration cutoff: trades strictly before %s (ts=%s)",
             cutoff_iso, cutoff_ts)

    # All wallets that traded the target market at any time. We use
    # them as the calibration population because they are the actual
    # population the simulator will reproduce.
    wallets = [
        row[0] for row in ch.client.execute(
            f"""
            SELECT DISTINCT proxy_wallet
            FROM polymetl.dataapi_trades
            WHERE condition_id = %(cid)s
            """,
            {"cid": meta["condition_id"]},
        )
    ]
    log.info("found %d distinct wallets in market %s", len(wallets), meta["condition_id"][:18])
    if not wallets:
        log.warning("no wallets in target market; calibration produced 0 rows")
        return 0

    rows: list[tuple] = []
    fetched_at = dt.datetime.utcnow()
    for i, wallet in enumerate(wallets, 1):
        trades = fetch_pre_event_trades(ch, wallet, cutoff_ts)
        if not trades:
            # Wallet's only activity is the target market itself.
            # Cannot calibrate a behavioral fingerprint from zero
            # pre-event trades. Skip — documented in EMPIRICAL_PRIORS.
            continue
        cids = list({c for c, _, _, _, _ in trades})
        resolved = fetch_resolved_lookup(ch, cids)
        feat = compute_features(trades, resolved)
        if i <= 10 or i % 50 == 0:
            log.info(
                "[%d/%d] %s tx=%d cap=$%.0f div=%d acc=%.2f n_res=%d",
                i, len(wallets), wallet[:10], feat["tx_count"],
                feat["capital_usd"], feat["asset_diversity"],
                feat["past_accuracy"], feat["n_resolved_prior"],
            )
        rows.append((
            wallet, meta["condition_id"], feat["capital_usd"],
            feat["tx_count"], feat["maker_ratio"],
            feat["avg_position_usd"], feat["asset_diversity"],
            feat["avg_holding_h"], feat["past_accuracy"],
            feat["n_resolved_prior"], fetched_at,
        ))

    if dry_run:
        log.info("dry-run: would insert %d rows", len(rows))
        return len(rows)

    ch.insert_wallet_features(rows)
    log.info("inserted %d wallet_features rows for %s", len(rows), slug)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    calibrate(slug=args.slug, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
