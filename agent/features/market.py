"""Market-level priors derivation (was src/population/derive_priors.py).

Emits `data/priors_<slug>.json` consumed by `agent.factory.init_agents`
and the experiment runner. Every value is a deterministic function of
ClickHouse state via `data.query.*`. See `docs/EMPIRICAL_PRIORS.md`
for the source SQL of every prior + the few explicit constants
(_EPS, _PRICE_FLOOR, _PRICE_CAP, n_ticks bounds, llm temperature 0).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path
from typing import Optional

from agent.features.temporal import n_ticks_for_lifetime
from data.query import markets as q_markets
from data.query import orderbook as q_orderbook
from data.query import prices as q_prices
from data.query import trades as q_trades
from data.store.clickhouse import ClickHouse


log = logging.getLogger(__name__)

# Numerical safeguards (NOT free hyperparameters).
_EPS = 1e-9
_PRICE_FLOOR = 0.01
_PRICE_CAP = 0.99


def derive_signal_mu(
    condition_id: str, yes_token_id: str, open_ts: int, hours: int = 24,
    ch=None,
) -> dict:
    """Volume-weighted YES price in the first `hours`.
    Tries clob_prices_history first; falls back to dataapi_trades VWAP.
    Returns {"vwap", "n_trades", "source", "hours"}."""
    out = q_prices.first_window_avg(yes_token_id, open_ts, hours, ch=ch)
    if out is not None:
        return out
    return q_trades.first_window_vwap(
        condition_id, outcome_index=0, t0=open_ts, hours=hours, ch=ch,
    )


def derive_bootstrap_book(
    condition_id: str, yes_token_id: str, open_ts: int, hours: int = 24,
    ch=None,
) -> dict:
    """Bootstrap orderbook anchor + spread + depth.
    Tries clob_orderbook; falls back to dataapi_trades dispersion."""
    out = q_orderbook.bootstrap_priors(yes_token_id, open_ts, hours, ch=ch)
    if out is not None:
        return out
    disp = q_trades.trade_dispersion(
        condition_id, outcome_index=0, t0=open_ts, hours=hours, ch=ch,
    )
    if disp["n"] == 0:
        log.warning("no first-window data for %s; bootstrap defaults to 0.5",
                    yes_token_id[:12])
        return {
            "anchor_yes": 0.5, "spread": 0.04, "depth_per_level": 100.0,
            "depth_levels": 3, "source": "fallback_default",
        }
    spread = max(0.01, disp["q75"] - disp["q25"])
    return {
        "anchor_yes": disp["mean"],
        "spread": round(spread, 2),
        "depth_per_level": disp["median_size"],
        "depth_levels": 3,
        "source": "dataapi_trades_dispersion",
    }


def derive_priors(slug: str, ch: Optional[ClickHouse] = None) -> dict:
    """Top-level: produce the priors dict for one market slug."""
    meta = q_markets.get_market_meta(slug, ch=ch)
    if meta is None:
        raise SystemExit(f"market slug {slug!r} not found in clob_markets")
    open_ts = q_trades.market_open_ts(meta["condition_id"], ch=ch)

    vwap = derive_signal_mu(
        meta["condition_id"], meta["yes_token_id"], open_ts, ch=ch,
    )
    book = derive_bootstrap_book(
        meta["condition_id"], meta["yes_token_id"], open_ts, ch=ch,
    )
    last_ts = q_trades.market_last_trade_ts(meta["condition_id"], ch=ch) \
              or (open_ts + 24 * 3600)
    n_ticks = n_ticks_for_lifetime(open_ts, last_ts)

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
        # Engine parameters (from clob_markets directly):
        "tick_size": meta["tick_size"],
        "taker_fee_bps": meta["taker_fee_bps"],
        # Sim execution parameters (derived):
        "n_ticks": n_ticks,
        # Private signal anchor:
        "signal_mu": vwap["vwap"],
        "signal_mu_meta": {
            "source": vwap["source"], "n_obs": vwap["n_trades"],
            "horizon_hours": vwap["hours"],
        },
        # Bootstrap orderbook seed:
        "bootstrap": book,
        "_eps": _EPS,
        "_price_floor": _PRICE_FLOOR,
        "_price_cap": _PRICE_CAP,
        "derived_at_iso": dt.datetime.utcnow().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--out-dir", default="data")
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
