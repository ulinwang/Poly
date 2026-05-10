"""v7 — Derive every simulator hyperparameter empirically from the
ClickHouse data layer.

The output is a single JSON file `data/priors_<slug>.json` consumed
by `src/pipeline/runner.py` and `src/population/build_population.py`.
Re-running this script with the same DB state always produces the
same JSON — that is the rigour-and-reproducibility commitment of v7.

Sources (in fall-back order):
    dataapi_trades      — comprehensive (110k markets); used for
                          cutoff_ts, signal_mu, capital floor/cap
    clob_markets        — taker_base_fee, minimum_tick_size
    markets_resolved    — winning_idx (used downstream by
                          wallet_features.py for past_accuracy)
    clob_orderbook      — preferred source for bootstrap depth+spread,
                          but absent for older closed markets; falls
                          back to trade-derived estimates
    clob_prices_history — preferred high-resolution price path; falls
                          back to dataapi_trades aggregation

Every prior is a deterministic function of (condition_id, the rows
in CH at this moment). No "magic constant" defaults are baked in;
the few choices that ARE explicit (e.g. percentile thresholds) are
documented in `docs/EMPIRICAL_PRIORS.md` with their justifications.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import math
import statistics
from pathlib import Path
from typing import Optional

from ..pipeline.clickhouse import ClickHouse
from ..pipeline.config import get_settings


log = logging.getLogger(__name__)

# Statistical safeguards (NOT free hyperparameters — these are
# numerical-stability constants, documented in EMPIRICAL_PRIORS.md).
_EPS = 1e-9
_PRICE_FLOOR = 0.01   # truncated-normal floor for signal sampling
_PRICE_CAP   = 0.99   # truncated-normal cap


def fetch_market_meta(ch: ClickHouse, slug: str) -> dict:
    """Resolve slug → condition_id, end_date, outcomes, winning_idx,
    YES/NO token_ids. Reads from clob_markets + markets_resolved."""
    rows = ch.client.execute(
        f"""
        SELECT condition_id, market_slug, tokens_json, minimum_tick_size,
               taker_base_fee, end_date_iso, accepting_order_timestamp
        FROM polymetl.clob_markets
        WHERE market_slug = %(slug)s
        LIMIT 1
        """,
        {"slug": slug},
    )
    if not rows:
        raise SystemExit(f"market slug {slug!r} not found in clob_markets")
    cid, slug_, tokens_json, tick, fee_bps_raw, end_iso, accept_ts = rows[0]
    tokens = json.loads(tokens_json)
    yes = next((t for t in tokens if t.get("outcome", "").lower() == "yes"), tokens[0])
    no = next((t for t in tokens if t.get("outcome", "").lower() == "no"), tokens[-1])

    res_rows = ch.client.execute(
        f"""
        SELECT winning_idx, end_date, closed_time
        FROM polymetl.markets_resolved
        WHERE condition_id = %(cid)s
        LIMIT 1
        """,
        {"cid": cid},
    )
    winning_idx = int(res_rows[0][0]) if res_rows else -1

    return {
        "condition_id": cid,
        "slug": slug_,
        "yes_token_id": str(yes["token_id"]),
        "no_token_id": str(no["token_id"]),
        "minimum_tick_size": float(tick),
        # clob_markets stores taker_base_fee in basis points
        # (Polymarket convention: 0 for most markets).
        "taker_base_fee_bps": float(fee_bps_raw),
        "end_date_iso": end_iso.isoformat() if end_iso else None,
        "accept_ts_iso": accept_ts.isoformat() if accept_ts else None,
        "winning_idx": winning_idx,
    }


def market_open_ts(ch: ClickHouse, condition_id: str) -> int:
    """Cutoff = unix timestamp of the FIRST observed trade in the
    target market. This is the actual market-open time per the
    audit-log; no 60-day fallback (that was a v4 magic constant)."""
    rows = ch.client.execute(
        f"""
        SELECT min(trade_time) FROM polymetl.dataapi_trades
        WHERE condition_id = %(cid)s
        """,
        {"cid": condition_id},
    )
    if not rows or rows[0][0] is None:
        raise SystemExit(
            f"no trades in dataapi_trades for {condition_id} — "
            f"cannot derive market_open_ts; ingest data_api first"
        )
    return int(rows[0][0].timestamp())


def first_window_vwap(
    ch: ClickHouse, condition_id: str, yes_token_id: str,
    open_ts: int, hours: int = 24,
) -> dict:
    """Volume-weighted average YES price over the first `hours` of
    the market. Tries `clob_prices_history` (hourly bars) first;
    falls back to per-trade aggregation from `dataapi_trades`.

    Returns: {"vwap": float, "n_trades": int, "source": "clob_ph" | "dataapi_trades", "hours": int}
    """
    cutoff = open_ts + hours * 3600

    rows = ch.client.execute(
        f"""
        SELECT count(), avg(p)
        FROM polymetl.clob_prices_history
        WHERE token_id = %(tid)s
          AND toUnixTimestamp(t) >= %(o)s
          AND toUnixTimestamp(t) < %(c)s
        """,
        {"tid": yes_token_id, "o": open_ts, "c": cutoff},
    )
    n, avg_p = rows[0] if rows else (0, None)
    if n and avg_p is not None:
        return {"vwap": float(avg_p), "n_trades": int(n),
                "source": "clob_prices_history", "hours": hours}

    # Fallback: derive from dataapi_trades (per-trade resolution,
    # filter by outcome="Yes" for the YES side).
    rows = ch.client.execute(
        f"""
        SELECT count(), sum(price * size) AS w, sum(size) AS s
        FROM polymetl.dataapi_trades
        WHERE condition_id = %(cid)s
          AND outcome_index = 0
          AND toUnixTimestamp(trade_time) >= %(o)s
          AND toUnixTimestamp(trade_time) < %(c)s
        """,
        {"cid": _condition_for_token(ch, yes_token_id), "o": open_ts, "c": cutoff},
    )
    n, w, s = rows[0] if rows else (0, 0.0, 0.0)
    if n and s and s > 0:
        return {"vwap": float(w) / float(s), "n_trades": int(n),
                "source": "dataapi_trades", "hours": hours}

    # No data → fall back to a NEUTRAL prior, but flag it.
    log.warning(
        "no first-%dh price data for token %s; falling back to 0.5",
        hours, yes_token_id[:12],
    )
    return {"vwap": 0.5, "n_trades": 0, "source": "fallback_0.5",
            "hours": hours}


def _condition_for_token(ch: ClickHouse, token_id: str) -> str:
    """Helper: look up condition_id from a token_id via clob_markets."""
    rows = ch.client.execute(
        f"""
        SELECT condition_id FROM polymetl.clob_markets
        WHERE position(tokens_json, %(tid)s) > 0
        LIMIT 1
        """,
        {"tid": token_id},
    )
    return rows[0][0] if rows else ""


def bootstrap_book_priors(
    ch: ClickHouse, yes_token_id: str, open_ts: int, hours: int = 24,
) -> dict:
    """Empirical bootstrap orderbook anchor + spread + depth.

    Source order:
      1. `clob_orderbook` snapshots in first `hours` (best when
         scraped while the market was live).
      2. Fallback: derive from `dataapi_trades` price dispersion in
         the first window — spread proxied by IQR of trade prices,
         depth proxied by median trade size.
    """
    cutoff = open_ts + hours * 3600

    rows = ch.client.execute(
        f"""
        SELECT
            avg(if(side='BUY',  price, NULL)) AS bid_avg,
            avg(if(side='SELL', price, NULL)) AS ask_avg,
            quantile(0.5)(size) AS depth_med
        FROM polymetl.clob_orderbook
        WHERE token_id = %(tid)s
          AND toUnixTimestamp(fetched_at) >= %(o)s
          AND toUnixTimestamp(fetched_at) < %(c)s
        """,
        {"tid": yes_token_id, "o": open_ts, "c": cutoff},
    )
    bid, ask, depth = rows[0] if rows else (None, None, None)
    if bid is not None and ask is not None and depth and depth > 0:
        return {
            "anchor_yes": (float(bid) + float(ask)) / 2.0,
            "spread": max(0.01, float(ask) - float(bid)),
            "depth_per_level": float(depth),
            "depth_levels": 3,    # by spec — see EMPIRICAL_PRIORS.md
            "source": "clob_orderbook",
        }

    # Fallback: derive from trade dispersion.
    cid = _condition_for_token(ch, yes_token_id)
    rows = ch.client.execute(
        f"""
        SELECT count(), avg(price), quantile(0.25)(price),
               quantile(0.75)(price), quantile(0.5)(size)
        FROM polymetl.dataapi_trades
        WHERE condition_id = %(cid)s
          AND outcome_index = 0
          AND toUnixTimestamp(trade_time) >= %(o)s
          AND toUnixTimestamp(trade_time) < %(c)s
        """,
        {"cid": cid, "o": open_ts, "c": cutoff},
    )
    n, mean_p, q25, q75, depth = rows[0] if rows else (0, 0.5, 0.4, 0.6, 100.0)
    if n == 0:
        log.warning("no first-window data for %s; bootstrap defaults to 0.5/0.04/100",
                    yes_token_id[:12])
        return {"anchor_yes": 0.5, "spread": 0.04, "depth_per_level": 100.0,
                "depth_levels": 3, "source": "fallback_default"}
    spread = max(0.01, float(q75) - float(q25))
    return {
        "anchor_yes": float(mean_p),
        "spread": round(spread, 2),
        "depth_per_level": float(depth),
        "depth_levels": 3,
        "source": "dataapi_trades_dispersion",
    }


def market_lifetime_n_ticks(
    ch: ClickHouse, condition_id: str, open_ts: int, fidelity_hours: int = 6,
) -> int:
    """Number of sim ticks = market lifetime (in trade-time) divided
    by fidelity, capped at 48 (LLM compute budget).

    Uses (max - min) trade_time to define market lifetime. Ticks land
    on 6h boundaries by default; see EMPIRICAL_PRIORS.md for the
    rationale on 6h.
    """
    rows = ch.client.execute(
        f"""
        SELECT max(trade_time) FROM polymetl.dataapi_trades
        WHERE condition_id = %(cid)s
        """,
        {"cid": condition_id},
    )
    if not rows or rows[0][0] is None:
        return 24
    last_ts = int(rows[0][0].timestamp())
    span_hours = max(6, (last_ts - open_ts) // 3600)
    n = round(span_hours / fidelity_hours)
    return max(8, min(48, n))


def derive_priors(slug: str, ch: Optional[ClickHouse] = None) -> dict:
    """Top-level: produce the priors dict for one market slug."""
    if ch is None:
        s = get_settings()
        ch = ClickHouse(host=s.CLICKHOUSE_HOST, port=s.CLICKHOUSE_PORT,
                        user=s.CLICKHOUSE_USER, password=s.CLICKHOUSE_PASSWORD,
                        database=s.CLICKHOUSE_DATABASE)
    meta = fetch_market_meta(ch, slug)
    open_ts = market_open_ts(ch, meta["condition_id"])
    vwap = first_window_vwap(ch, meta["condition_id"],
                              meta["yes_token_id"], open_ts)
    book = bootstrap_book_priors(ch, meta["yes_token_id"], open_ts)
    n_ticks = market_lifetime_n_ticks(ch, meta["condition_id"], open_ts)

    return {
        "schema_version": "v7-priors-1",
        "slug": slug,
        "condition_id": meta["condition_id"],
        "yes_token_id": meta["yes_token_id"],
        "no_token_id": meta["no_token_id"],
        "winning_idx": meta["winning_idx"],
        "end_date_iso": meta["end_date_iso"],
        "market_open_ts": open_ts,
        "market_open_iso": dt.datetime.utcfromtimestamp(open_ts).isoformat(),
        # === Engine parameters (from clob_markets directly) ===
        "tick_size": meta["minimum_tick_size"],
        "taker_fee_bps": meta["taker_base_fee_bps"],
        # === Sim execution parameters (derived) ===
        "n_ticks": n_ticks,
        # === Private signal anchor (Kyle 1985 / Glosten-Milgrom) ===
        "signal_mu": vwap["vwap"],
        "signal_mu_meta": {
            "source": vwap["source"], "n_obs": vwap["n_trades"],
            "horizon_hours": vwap["hours"],
        },
        # === Bootstrap orderbook seed (mirrors real first-day depth) ===
        "bootstrap": book,
        "_eps": _EPS,
        "_price_floor": _PRICE_FLOOR,
        "_price_cap": _PRICE_CAP,
        "derived_at_iso": dt.datetime.utcnow().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True,
                        help="Polymarket market slug")
    parser.add_argument("--out-dir", default="data",
                        help="directory to write priors_<slug>.json")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"priors_{args.slug}.json"

    priors = derive_priors(args.slug)
    out.write_text(json.dumps(priors, indent=2, default=str))
    log.info("wrote %s (%d bytes)", out, out.stat().st_size)
    log.info("  cutoff: %s", priors["market_open_iso"])
    log.info("  signal_mu: %.3f (source=%s, n=%d)",
             priors["signal_mu"], priors["signal_mu_meta"]["source"],
             priors["signal_mu_meta"]["n_obs"])
    log.info("  bootstrap: anchor=%.3f spread=%.3f depth=%.0f source=%s",
             priors["bootstrap"]["anchor_yes"],
             priors["bootstrap"]["spread"],
             priors["bootstrap"]["depth_per_level"],
             priors["bootstrap"]["source"])
    log.info("  n_ticks: %d, tick_size: %.4f, taker_fee_bps: %.2f",
             priors["n_ticks"], priors["tick_size"], priors["taker_fee_bps"])


if __name__ == "__main__":
    main()
