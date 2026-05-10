"""Per-wallet pre-event feature aggregation.

`compute_features` is a pure function over rows already pulled from
`data.query.wallets`. `calibrate` is the persistence step that
upserts `wallet_features` rows for every wallet that traded the
target market.

v8: SQL is delegated to `data.query.wallets` and
`data.query.trades.market_open_ts`; this module owns only the
feature math + persistence.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import statistics
from typing import Optional

from data.query._ch import get_ch
from data.query import markets as q_markets
from data.query import trades as q_trades
from data.query import wallets as q_wallets
from data.store.clickhouse import ClickHouse

log = logging.getLogger(__name__)


def compute_features(
    trades: list[tuple], resolved_lookup: dict[str, int],
) -> dict:
    """Aggregate one wallet's pre-event activity.

    `trades` rows: (condition_id, outcome_index, price, size, trade_time)
    `resolved_lookup`: condition_id → winning_idx (0/1/-1)

    See docs/EMPIRICAL_PRIORS.md for source SQL of every field.
    `maker_ratio` and `avg_holding_h` cannot be inferred from
    dataapi_trades; v8 keeps them as 0.0 placeholders for schema
    parity (NOT consumed by calibrated.persona prompts).
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
    # this wallet was on the winning side of.
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
        "maker_ratio": 0.0,
        "avg_position_usd": avg_position_usd,
        "asset_diversity": asset_diversity,
        "avg_holding_h": 0.0,
        "past_accuracy": past_accuracy,
        "n_resolved_prior": n_resolved_prior,
    }


def calibrate(
    slug: str, dry_run: bool = False, ch: Optional[ClickHouse] = None,
) -> int:
    """Build wallet_features rows for every wallet in `slug`.
    Returns the number of rows inserted.

    All SQL via `data.query.*`. The wallet → features → INSERT path
    here is the only writer to `wallet_features`."""
    ch = get_ch(ch)
    ch.ensure_sim_schema()
    ch.ensure_wallet_features_schema()

    meta = q_markets.get_market_meta(slug, ch=ch)
    if meta is None:
        raise SystemExit(f"market {slug!r} not found in clob_markets")
    cutoff_ts = q_trades.market_open_ts(meta["condition_id"], ch=ch)
    cutoff_iso = dt.datetime.utcfromtimestamp(cutoff_ts).isoformat()
    log.info("calibration cutoff: trades strictly before %s (ts=%s)",
             cutoff_iso, cutoff_ts)

    addrs = q_wallets.list_wallets_in_market(meta["condition_id"], ch=ch)
    log.info("found %d wallets in %s", len(addrs), meta["condition_id"][:18])
    if not addrs:
        log.warning("no wallets; nothing to calibrate")
        return 0

    rows: list[tuple] = []
    fetched_at = dt.datetime.utcnow()
    for i, wallet in enumerate(addrs, 1):
        trades = q_wallets.get_pre_event_trades(wallet, cutoff_ts, ch=ch)
        if not trades:
            continue
        cids = list({c for c, _, _, _, _ in trades})
        resolved = q_wallets.get_resolved_outcomes(cids, ch=ch)
        feat = compute_features(trades, resolved)
        if i <= 10 or i % 50 == 0:
            log.info(
                "[%d/%d] %s tx=%d cap=$%.0f div=%d acc=%.2f n_res=%d",
                i, len(addrs), wallet[:10], feat["tx_count"],
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
