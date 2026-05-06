"""
v4 Phase 3 — Build the agent population for a calibrated simulation.

Combines:
  1. wallet_features rows (Phase 1)         — capital + behavioral fingerprint
  2. wallet_personas.json cache (Phase 2)   — LLM-generated profile_text
  3. pre-event consensus from market trades — for the private signal mu
  4. past_accuracy → signal sigma           — informed/uninformed mix

Output: list[AgentInit]. The simulator (env.py) consumes this directly.
"""
from __future__ import annotations

import datetime as dt
import logging
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..clickhouse_client import ClickHouse
from ..config import get_settings
from .persona_generator import CACHE_PATH, load_cache


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentInit:
    """Concrete spec to instantiate one simulator agent."""
    wallet_addr: str             # source wallet (for traceability)
    persona_type: str            # "Calibrated" — replaces ex-ante role label
    capital_initial: float       # USD start
    profile_text: str            # behavioral profile from Phase 2
    private_signal_mu: float     # in [0.01, 0.99]
    private_signal_sigma: float  # in [0.05, 0.4]
    risk_aversion: float         # 0..1, derived from past behavior
    # Source features for SERD baseline benchmark (paper Table 5):
    src_tx_count: int
    src_maker_ratio: float
    src_avg_position_usd: float
    src_asset_diversity: int


def derive_signal_sigma(past_accuracy: float) -> float:
    """Higher empirical accuracy → tighter prior. Bounds enforced."""
    sigma = 0.4 * (1.0 - past_accuracy)
    return max(0.05, min(0.4, sigma))


def derive_risk_aversion(maker_ratio: float, avg_holding_h: float) -> float:
    """A heuristic, not a label. Higher maker_ratio (passive) and longer
    holding time both correlate with risk aversion.

    risk_aversion = clip(0.5 * maker_ratio + 0.5 * tanh(avg_holding_h/24), 0, 1)
    """
    # statistics.NormalDist().cdf approximates tanh ramp tightly enough
    hold_norm = 1.0 - 1.0 / (1.0 + max(avg_holding_h, 0.0) / 24.0)
    raw = 0.5 * max(0.0, min(1.0, maker_ratio)) + 0.5 * hold_norm
    return max(0.0, min(1.0, raw))


def pre_event_consensus_p(
    ch: ClickHouse, market_id: str, yes_token_id: str,
    horizon_hours: float = 24.0,
) -> float:
    """Volume-weighted average YES price over the first `horizon_hours`
    of trade history for the YES token. Strictly ex-ante for any agent
    decision — the trades happened, the resolution did not."""
    rows = ch.client.execute(
        f"""
        SELECT min(trade_time) AS t0
        FROM {ch.database}.market_trade_history
        WHERE market_id = %(mid)s AND token_id = %(tid)s
        """,
        {"mid": str(market_id), "tid": str(yes_token_id)},
    )
    if not rows or rows[0][0] is None:
        return 0.5
    t0: dt.datetime = rows[0][0]
    cutoff = t0 + dt.timedelta(hours=horizon_hours)
    rows = ch.client.execute(
        f"""
        SELECT price, size
        FROM {ch.database}.market_trade_history
        WHERE market_id = %(mid)s AND token_id = %(tid)s
              AND trade_time < %(cut)s
        """,
        {"mid": str(market_id), "tid": str(yes_token_id), "cut": cutoff},
    )
    if not rows:
        return 0.5
    weighted = sum(p * s for p, s in rows)
    total_size = sum(s for _, s in rows)
    if total_size <= 0:
        return statistics.fmean(p for p, _ in rows) if rows else 0.5
    return max(0.01, min(0.99, weighted / total_size))


def draw_private_signal(
    mu: float, sigma: float, rng: random.Random,
) -> float:
    """Truncated normal in (0.01, 0.99)."""
    for _ in range(64):
        s = rng.gauss(mu, sigma)
        if 0.01 < s < 0.99:
            return s
    # Fallback if the gauss draws keep bouncing out
    return max(0.01, min(0.99, mu))


def build_population(
    target_market_id: str,
    yes_token_id: str,
    capital_scale: float = 1.0,
    capital_floor_usd: float = 50.0,
    capital_cap_usd: float = 50_000.0,
    seed: int = 0,
    cache_path: Path = CACHE_PATH,
    ch: Optional[ClickHouse] = None,
) -> list[AgentInit]:
    """Materialize the AgentInit population for the calibrated sim."""
    settings = get_settings()
    if ch is None:
        ch = ClickHouse(
            host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )

    feature_rows = ch.fetch_wallet_features(target_market_id)
    if not feature_rows:
        log.warning("no wallet_features rows for market %s", target_market_id)
        return []
    cache = load_cache(cache_path).get(str(target_market_id), {})

    consensus_mu = pre_event_consensus_p(ch, target_market_id, yes_token_id)
    log.info("pre-event consensus YES p ≈ %.3f", consensus_mu)

    rng = random.Random(seed)
    population: list[AgentInit] = []
    for r in feature_rows:
        wallet, capital_usd, tx_count, maker_ratio, avg_pos, \
            asset_diversity, avg_holding_h, past_accuracy, n_resolved_prior = r

        cached = cache.get(wallet)
        if not cached or not cached.get("ok"):
            log.warning("no cached profile for %s — skipped", wallet[:10])
            continue

        capital = max(
            capital_floor_usd,
            min(capital_cap_usd, float(capital_usd) * capital_scale),
        )
        sigma = derive_signal_sigma(float(past_accuracy))
        signal = draw_private_signal(consensus_mu, sigma, rng)
        risk_aversion = derive_risk_aversion(
            float(maker_ratio), float(avg_holding_h),
        )

        population.append(AgentInit(
            wallet_addr=wallet,
            persona_type="Calibrated",
            capital_initial=capital,
            profile_text=cached["profile_text"],
            private_signal_mu=signal,
            private_signal_sigma=sigma,
            risk_aversion=risk_aversion,
            src_tx_count=int(tx_count),
            src_maker_ratio=float(maker_ratio),
            src_avg_position_usd=float(avg_pos),
            src_asset_diversity=int(asset_diversity),
        ))
    log.info(
        "built population of %s agents (capital range $%.0f..$%.0f, mu range %.2f..%.2f)",
        len(population),
        min((a.capital_initial for a in population), default=0.0),
        max((a.capital_initial for a in population), default=0.0),
        min((a.private_signal_mu for a in population), default=0.0),
        max((a.private_signal_mu for a in population), default=0.0),
    )
    return population
