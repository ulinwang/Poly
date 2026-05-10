"""
v4 Phase 1 — Empirical wallet calibration.

For a target Polymarket market that has already resolved, identify the
real wallets that traded it, then summarize each wallet's *pre-market*
behavioral fingerprint using only data observable BEFORE the market
opened. Output is written to ClickHouse `wallet_features` for use by
the agent initializer.

Strict constraint: nothing fetched here may include data dated at or
after the target market's `start_date`. This keeps agent initialization
free of look-ahead leakage from the very market we are simulating.

Usage:
    uv run python -m src.sim.wallet_calibration \\
        --slug will-the-chopsticks-... --n-wallets 20

Data sources:
    Polymarket data-api `/trades?user=<addr>` — full trade history
    Polymarket data-api `/closed-positions?user=<addr>` — past PnL
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import random
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Iterable, Optional

from ..pipeline.clickhouse import ClickHouse
from ..pipeline.config import get_settings
from . import trade_history as clob_history


DATA_API_BASE = "https://data-api.polymarket.com"
USER_AGENT = "polymetl-sim/0.1"

log = logging.getLogger(__name__)


# ----- HTTP helpers -----------------------------------------------------------


def _http_get_json(url: str, timeout: float = 30.0) -> object:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_user_trades(
    wallet: str, before_ts: int, page_size: int = 500, max_pages: int = 20,
    sleep: float = 0.2,
) -> list[dict]:
    """All trades for a wallet whose timestamp < before_ts."""
    all_trades: list[dict] = []
    offset = 0
    for _ in range(max_pages):
        params = {"user": wallet, "limit": page_size, "offset": offset, "takerOnly": "false"}
        url = f"{DATA_API_BASE}/trades?{urllib.parse.urlencode(params)}"
        try:
            page = _http_get_json(url)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 422):
                break
            raise
        if not isinstance(page, list) or not page:
            break
        # Filter to before_ts
        kept = [t for t in page if int(t.get("timestamp") or 0) < before_ts]
        all_trades.extend(kept)
        # If the page's oldest trade is already before our cutoff or page empty, stop.
        if len(page) < page_size:
            break
        offset += page_size
        if sleep:
            time.sleep(sleep)
    return all_trades


def fetch_user_closed_positions(
    wallet: str, before_ts: int, page_size: int = 50, max_pages: int = 10,
    sleep: float = 0.2,
) -> list[dict]:
    """Closed positions for a wallet that resolved (endDate) before before_ts."""
    out: list[dict] = []
    offset = 0
    for _ in range(max_pages):
        params = {
            "user": wallet, "limit": page_size, "offset": offset,
            "sortBy": "TIMESTAMP", "sortDirection": "DESC",
        }
        url = f"{DATA_API_BASE}/closed-positions?{urllib.parse.urlencode(params)}"
        try:
            page = _http_get_json(url)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 422):
                break
            raise
        if not isinstance(page, list) or not page:
            break
        for p in page:
            end_iso = p.get("endDate")
            try:
                end_ts = int(dt.datetime.fromisoformat(
                    end_iso.replace("Z", "+00:00")
                ).timestamp()) if isinstance(end_iso, str) else 0
            except ValueError:
                end_ts = 0
            if 0 < end_ts < before_ts:
                out.append(p)
        if len(page) < page_size:
            break
        offset += page_size
        if sleep:
            time.sleep(sleep)
    return out


# ----- Feature extraction -----------------------------------------------------


def _to_float(x: object, default: float = 0.0) -> float:
    try:
        return float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def compute_features(trades: list[dict], closed_positions: list[dict]) -> dict:
    """Aggregate one wallet's pre-event activity into the feature
    schema persisted to `wallet_features`.

    Honest-feature-set policy. The Polymarket data-api does NOT expose
    the maker/taker label for individual trades (the `takerOnly`
    parameter merely switches whether the user appears as taker; the
    counterparty role is never returned). Likewise, /closed-positions
    does not include open/close timestamps. We therefore set:

      maker_ratio  = 0.0   (NOT INFERABLE — placeholder column)
      avg_holding_h = 0.0  (NOT INFERABLE — placeholder column)

    They remain in the schema for forward-compat (a future on-chain ETL
    can populate them with truth), but the v4 simulator's
    `initialization.py` does not consume them. See
    docs/EXPERIMENT_LOG.md §"Honest features" for the methodology
    rationale.
    """
    tx_count = len(trades)
    if tx_count == 0:
        return {
            "capital_usd": 0.0, "tx_count": 0, "maker_ratio": 0.0,
            "avg_position_usd": 0.0, "asset_diversity": 0,
            "avg_holding_h": 0.0, "past_accuracy": 0.0,
            "n_resolved_prior": 0,
        }

    # Capital deployed: sum of past notionals as a robust upper bound
    # on the wallet's cumulative exposure (paper Eq. 5 uses max abs
    # cumulative position; without per-trade timestamps for the running
    # sum we use the bound).
    notionals = [_to_float(t.get("price")) * _to_float(t.get("size")) for t in trades]
    capital_usd = max(sum(notionals), 0.0)
    avg_position_usd = statistics.fmean(notionals) if notionals else 0.0

    # Asset diversity: distinct conditionId across all trades.
    asset_diversity = len({t.get("conditionId") for t in trades if t.get("conditionId")})

    # Past accuracy: capital-weighted fraction of closed positions that
    # ended profitable. Uses realizedPnl > 0 as the success indicator.
    n_resolved_prior = len(closed_positions)
    if n_resolved_prior == 0:
        past_accuracy = 0.0
    else:
        win_capital = 0.0
        total_capital = 0.0
        for p in closed_positions:
            cap = abs(_to_float(p.get("avgPrice")) * _to_float(p.get("totalBought")))
            total_capital += cap
            if _to_float(p.get("realizedPnl")) > 0:
                win_capital += cap
        past_accuracy = (win_capital / total_capital) if total_capital > 0 else 0.0

    return {
        "capital_usd": capital_usd,
        "tx_count": tx_count,
        # Placeholders — see docstring; not consumed by initialization.py
        "maker_ratio": 0.0,
        "avg_holding_h": 0.0,
        "avg_position_usd": avg_position_usd,
        "asset_diversity": asset_diversity,
        "past_accuracy": past_accuracy,
        "n_resolved_prior": n_resolved_prior,
    }


# ----- Sampling ---------------------------------------------------------------


def stratified_sample(wallets: list[str], n: int, seed: int = 0) -> list[str]:
    """Return up to n wallets. If len(wallets) > n, take everyone (no
    randomness needed since we sort upstream by volume in SQL). Otherwise
    return all."""
    if n <= 0:
        return []
    if len(wallets) <= n:
        return list(wallets)
    rng = random.Random(seed)
    pool = list(wallets)
    rng.shuffle(pool)
    return pool[:n]


# ----- Top-level orchestration ------------------------------------------------


def market_meta(ch: ClickHouse, slug: str) -> tuple[str, dict]:
    row = ch.fetch_market_by_slug(slug)
    if not row:
        raise SystemExit(f"market {slug!r} not found in markets table")
    market_id, slug_, question, description, outcomes, clob_token_ids, \
        outcome_prices, volume, end_date, closed = row
    if end_date is None:
        raise SystemExit(f"market {slug!r} has no end_date")
    return market_id, {
        "slug": slug_, "question": question, "description": description,
        "outcomes": list(outcomes), "clob_token_ids": list(clob_token_ids),
        "outcome_prices": list(outcome_prices),
        "volume": _to_float(volume), "end_date": end_date, "closed": bool(closed),
    }


def market_open_cutoff(
    ch: ClickHouse, market_id: str, end_date: dt.datetime,
    fallback_days_before_end: Optional[int] = None,
) -> int:
    """Return the unix timestamp of the target market's first on-chain
    trade — i.e. when the market opened. This is the *correct* cutoff
    for wallet calibration: any wallet activity strictly < this ts is
    pre-event and free of look-ahead leakage.

    If `market_trade_history` has no rows for this market, raises
    SystemExit unless `fallback_days_before_end` is provided (in which
    case cutoff = end_date − that_many_days; for markets where you
    explicitly accept that some pre-event 'history' may include the
    very early days of the target market itself).
    """
    rows = ch.client.execute(
        f"""
        SELECT min(trade_time) FROM {ch.database}.market_trade_history
        WHERE market_id = %(mid)s
        """,
        {"mid": str(market_id)},
    )
    first_trade = rows[0][0] if rows else None
    if first_trade is None:
        if fallback_days_before_end is None:
            raise SystemExit(
                f"market {market_id} has no rows in market_trade_history; "
                f"call clob_history.fetch_and_store_trades(market_id, token_id) "
                f"before calibrating, OR pass --cutoff-days-before-end as a "
                f"fallback (will use end_date - N days, less rigorous)."
            )
        cutoff_ts = int(end_date.timestamp()) - fallback_days_before_end * 86400
        log.warning(
            "no market_trade_history rows; falling back to end_date - %dd cutoff "
            "(may include some target-market data if its lifetime > %dd)",
            fallback_days_before_end, fallback_days_before_end,
        )
        return cutoff_ts
    return int(first_trade.timestamp())


def calibrate(
    slug: str, n_wallets: int = 20,
    fallback_cutoff_days_before_end: Optional[int] = None,
    ensure_trade_history: bool = True, dry_run: bool = False,
    seed: int = 0,
) -> int:
    settings = get_settings()
    ch = ClickHouse(
        host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
        user=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DATABASE,
    )
    ch.ensure_sim_schema()
    ch.ensure_wallet_features_schema()

    market_id, market = market_meta(ch, slug)

    # Pre-fetch the target market's trade history. This is REQUIRED so
    # we can (a) enumerate participating wallets and (b) compute the
    # market-open cutoff from the first real trade.
    #
    # The data-api /trades?market= filter expects an on-chain
    # conditionId; our markets table doesn't store that field, so we
    # query Gamma at calibration time.
    if ensure_trade_history and market["clob_token_ids"]:
        condition_id = clob_history.fetch_condition_id(slug)
        if not condition_id:
            raise SystemExit(
                f"could not resolve conditionId for slug {slug!r} via Gamma API; "
                f"the data-api /trades?market= filter will not work without it"
            )
        log.info("conditionId for %s = %s...", slug, condition_id[:18])
        for token_id in market["clob_token_ids"]:
            log.info("fetching CLOB trade history for token %s...", token_id[:14] + "...")
            try:
                clob_history.fetch_and_store_trades(
                    ch, market_id, token_id, condition_id=condition_id,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("CLOB fetch failed for %s: %s", token_id[:14], exc)

    cutoff_ts = market_open_cutoff(
        ch, market_id, market["end_date"],
        fallback_days_before_end=fallback_cutoff_days_before_end,
    )
    cutoff_iso = dt.datetime.utcfromtimestamp(cutoff_ts).isoformat()
    log.info(
        "calibration cutoff: trades strictly before %s (ts=%s) — "
        "= market open per first observed trade",
        cutoff_iso, cutoff_ts,
    )

    wallets = ch.fetch_wallets_in_market(market_id)
    log.info("found %s distinct wallets in market %s", len(wallets), market_id)
    if not wallets:
        log.warning("no wallets found; calibration produced 0 rows")
        return 0
    sample = stratified_sample(wallets, n_wallets, seed=seed)
    log.info("calibrating sample of %s wallets (cutoff %s)", len(sample), cutoff_iso)

    rows: list[tuple] = []
    fetched_at = dt.datetime.utcnow()
    for i, w in enumerate(sample, 1):
        try:
            trades = fetch_user_trades(w, before_ts=cutoff_ts)
            closed = fetch_user_closed_positions(w, before_ts=cutoff_ts)
        except Exception as exc:  # noqa: BLE001
            log.warning("[%s/%s] %s skipped: %s", i, len(sample), w[:10], exc)
            continue
        feat = compute_features(trades, closed)
        log.info(
            "[%s/%s] %s tx=%d cap=$%.0f mkr=%.2f div=%d acc=%.2f n_res=%d",
            i, len(sample), w[:10], feat["tx_count"], feat["capital_usd"],
            feat["maker_ratio"], feat["asset_diversity"],
            feat["past_accuracy"], feat["n_resolved_prior"],
        )
        if feat["tx_count"] < 5 or feat["n_resolved_prior"] < 1:
            # Too thin for meaningful behavioral fingerprint
            continue
        rows.append((
            w, market_id, feat["capital_usd"], feat["tx_count"],
            feat["maker_ratio"], feat["avg_position_usd"],
            feat["asset_diversity"], feat["avg_holding_h"],
            feat["past_accuracy"], feat["n_resolved_prior"], fetched_at,
        ))

    if dry_run:
        log.info("dry-run: would insert %s rows into wallet_features", len(rows))
        return len(rows)
    ch.insert_wallet_features(rows)
    log.info("done; %s wallet feature rows inserted for market %s", len(rows), market_id)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate v4 simulator agents from real Polymarket wallets",
    )
    parser.add_argument("--slug", required=True)
    parser.add_argument("--n-wallets", type=int, default=20)
    parser.add_argument(
        "--fallback-cutoff-days-before-end", type=int, default=None,
        help="ONLY used as a fallback when market_trade_history is empty "
             "(prefer running clob_history.fetch_and_store_trades first). "
             "Default behavior (recommended): use the timestamp of the "
             "first observed trade in the target market as the cutoff.",
    )
    parser.add_argument("--no-trade-history", action="store_true",
                        help="skip pre-fetching market_trade_history (assume already populated)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    calibrate(
        slug=args.slug, n_wallets=args.n_wallets,
        fallback_cutoff_days_before_end=args.fallback_cutoff_days_before_end,
        ensure_trade_history=not args.no_trade_history,
        dry_run=args.dry_run, seed=args.seed,
    )


if __name__ == "__main__":
    main()
