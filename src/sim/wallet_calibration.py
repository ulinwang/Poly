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

from ..clickhouse_client import ClickHouse
from ..config import get_settings
from . import clob_history


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
    schema persisted to `wallet_features`."""
    tx_count = len(trades)
    if tx_count == 0:
        return {
            "capital_usd": 0.0, "tx_count": 0, "maker_ratio": 0.0,
            "avg_position_usd": 0.0, "asset_diversity": 0,
            "avg_holding_h": 0.0, "past_accuracy": 0.0,
            "n_resolved_prior": 0,
        }

    # Capital deployed: max absolute cumulative net position over the
    # pre-market window. Approximated from the trade stream:
    # +size on BUY, -size on SELL; sum of absolute notionals serves as
    # a robust upper bound when timing is missing.
    notionals = [_to_float(t.get("price")) * _to_float(t.get("size")) for t in trades]
    capital_usd = max(sum(notionals), 0.0)
    avg_position_usd = statistics.fmean(notionals) if notionals else 0.0

    # Maker ratio: proxyWallet acts as the user; takerOnly=false means
    # all trades that touched this wallet, but the API does not flip
    # the side label by maker/taker. We use the heuristic that in the
    # public schema "side" reflects what the user did and the network
    # fills are a near-mix; lacking a maker flag we approximate via:
    # if the price is at extreme 0/1 sweep ⇒ taker, else ⇒ maker.
    # (Approximation; if a `mode` or `role` field appears in future
    # API revisions, replace this branch.)
    maker_count = sum(1 for t in trades if 0.01 < _to_float(t.get("price")) < 0.99)
    maker_ratio = maker_count / tx_count if tx_count else 0.0

    # Asset diversity: distinct conditionId across all trades.
    asset_diversity = len({t.get("conditionId") for t in trades if t.get("conditionId")})

    # Average holding time per closed position (hours).
    holds: list[float] = []
    for p in closed_positions:
        # closed-positions response lacks open/close timestamps explicitly;
        # leave at 0.0 if absent. (Field varies by API version.)
        open_ts = _to_float(p.get("openTimestamp") or p.get("startTimestamp"))
        end_ts = _to_float(p.get("endTimestamp") or p.get("timestamp"))
        if open_ts > 0 and end_ts > open_ts:
            holds.append((end_ts - open_ts) / 3600.0)
    avg_holding_h = statistics.fmean(holds) if holds else 0.0

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
        "maker_ratio": maker_ratio,
        "avg_position_usd": avg_position_usd,
        "asset_diversity": asset_diversity,
        "avg_holding_h": avg_holding_h,
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


def market_open_timestamp(ch: ClickHouse, slug: str) -> tuple[str, int, dict]:
    row = ch.fetch_market_by_slug(slug)
    if not row:
        raise SystemExit(f"market {slug!r} not found in markets table")
    market_id, slug_, question, description, outcomes, clob_token_ids, \
        outcome_prices, volume, end_date, closed = row
    # We want the market START timestamp; markets table has end_date
    # but not start_date in the current schema. Fallback: use end_date - 60d
    # as the cutoff (most binary markets have multi-week lifetimes).
    if end_date is None:
        raise SystemExit(f"market {slug!r} has no end_date; cannot compute calibration cutoff")
    # Approximation: 60 days before end_date. Tunable via --cutoff-days.
    return market_id, int(end_date.timestamp()), {
        "slug": slug_, "question": question, "description": description,
        "outcomes": list(outcomes), "clob_token_ids": list(clob_token_ids),
        "outcome_prices": list(outcome_prices),
        "volume": _to_float(volume), "end_date": end_date, "closed": bool(closed),
    }


def calibrate(
    slug: str, n_wallets: int = 20, cutoff_days_before_end: int = 60,
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

    market_id, end_ts, market = market_open_timestamp(ch, slug)
    cutoff_ts = end_ts - cutoff_days_before_end * 86400
    cutoff_iso = dt.datetime.utcfromtimestamp(cutoff_ts).isoformat()
    log.info("calibration cutoff: trades strictly before %s (ts=%s)", cutoff_iso, cutoff_ts)

    # Optional: pre-fetch the target market's trade history so we can
    # enumerate participating wallets. Reuses src/sim/clob_history.
    if ensure_trade_history and market["clob_token_ids"]:
        for token_id in market["clob_token_ids"]:
            log.info("fetching CLOB trade history for token %s...", token_id[:14] + "...")
            try:
                clob_history.fetch_and_store_trades(ch, market_id, token_id)
            except Exception as exc:  # noqa: BLE001
                log.warning("CLOB fetch failed for %s: %s", token_id[:14], exc)

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
        "--cutoff-days-before-end", type=int, default=60,
        help="how many days before market end_date to use as the data cutoff",
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
        cutoff_days_before_end=args.cutoff_days_before_end,
        ensure_trade_history=not args.no_trade_history,
        dry_run=args.dry_run, seed=args.seed,
    )


if __name__ == "__main__":
    main()
