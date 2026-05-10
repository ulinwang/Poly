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
import json
import logging
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from data.store.clickhouse import ClickHouse
from data.store.config import get_settings
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


def derive_signal_sigma(
    past_accuracy: float, scale: float | None = None,
    floor: float | None = None, cap: float | None = None,
) -> float:
    """Higher empirical accuracy → tighter prior. Bounds enforced.

    Defaults from `Settings.SIGMA_*`; pass overrides for testing.
    """
    s = get_settings()
    scale = s.SIGMA_SCALE if scale is None else scale
    floor = s.SIGMA_FLOOR if floor is None else floor
    cap = s.SIGMA_CAP if cap is None else cap
    sigma = scale * (1.0 - past_accuracy)
    return max(floor, min(cap, sigma))


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
    consensus_mu: float | None = None,
    capital_scale: float = 1.0,
    capital_floor_usd: float | None = None,
    capital_cap_usd: float | None = None,
    seed: int = 0,
    cache_path: Path = CACHE_PATH,
    ch: Optional[ClickHouse] = None,
) -> list[AgentInit]:
    """Materialize the AgentInit population for the calibrated sim.

    `consensus_mu`: REQUIRED — must be supplied by the caller (v7
    flow loads it from `data/priors_<slug>.json` via
    `build_population_from_priors`). The runner passes it in so the
    same value can also seed the bootstrap orderbook anchor.

    Note: agent.risk_aversion is set to a neutral 0.5 placeholder. The
    v4 prompt for calibrated agents does not consume risk_aversion;
    behavioral preferences flow exclusively through profile_text and
    the private signal. (See audit log: prior heuristic
    `derive_risk_aversion(maker_ratio, holding_h)` was removed because
    those source fields are not extractable from the public data-api.)
    """
    settings = get_settings()
    if ch is None:
        ch = ClickHouse(
            host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )

    cap_floor = settings.CAPITAL_FLOOR_USD if capital_floor_usd is None else capital_floor_usd
    cap_cap = settings.CAPITAL_CAP_USD if capital_cap_usd is None else capital_cap_usd

    feature_rows = ch.fetch_wallet_features(target_market_id)
    if not feature_rows:
        log.warning("no wallet_features rows for market %s", target_market_id)
        return []
    cache = load_cache(cache_path).get(str(target_market_id), {})

    if consensus_mu is None:
        raise SystemExit(
            "consensus_mu must be supplied (read it from priors JSON via "
            "`build_population_from_priors(slug)`); v7 dropped the legacy "
            "market_trade_history fallback."
        )
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
            cap_floor, min(cap_cap, float(capital_usd) * capital_scale),
        )
        sigma = derive_signal_sigma(float(past_accuracy))
        signal = draw_private_signal(consensus_mu, sigma, rng)

        population.append(AgentInit(
            wallet_addr=wallet,
            persona_type="Calibrated",
            capital_initial=capital,
            profile_text=cached["profile_text"],
            private_signal_mu=signal,
            private_signal_sigma=sigma,
            # Neutral placeholder — not used in calibrated prompt path.
            risk_aversion=0.5,
            src_tx_count=int(tx_count),
            src_maker_ratio=float(maker_ratio),     # honest 0.0 from API
            src_avg_position_usd=float(avg_pos),
            src_asset_diversity=int(asset_diversity),
        ))
    log.info(
        "built population of %s agents (capital range $%.0f..$%.0f, "
        "mu range %.2f..%.2f, consensus_mu=%.3f)",
        len(population),
        min((a.capital_initial for a in population), default=0.0),
        max((a.capital_initial for a in population), default=0.0),
        min((a.private_signal_mu for a in population), default=0.0),
        max((a.private_signal_mu for a in population), default=0.0),
        consensus_mu,
    )
    return population


def load_priors(slug: str, data_dir: Path = Path("data")) -> dict:
    """Load `data/priors_<slug>.json` produced by derive_priors.py."""
    path = data_dir / f"priors_{slug}.json"
    if not path.exists():
        raise SystemExit(
            f"priors not found at {path}; run "
            f"`python scripts/03_derive_calibration_priors.py --slug {slug}` first"
        )
    return json.loads(path.read_text())


def build_population_from_priors(
    slug: str, seed: int = 0,
    cache_path: Path = CACHE_PATH,
    data_dir: Path = Path("data"),
    ch: Optional[ClickHouse] = None,
) -> tuple[list[AgentInit], dict]:
    """v7 entry point: load priors JSON, then build the population
    using ALL data-derived parameters (no Settings defaults). Returns
    (population, priors_dict) — runner uses `priors_dict` to also
    seed the bootstrap orderbook.
    """
    priors = load_priors(slug, data_dir=data_dir)

    # Derive empirical capital floor / cap from THIS market's wallet
    # population (5th and 95th percentiles of capital_usd in
    # wallet_features). Per v7 plan, no fixed $50/$50 000 defaults.
    settings = get_settings()
    if ch is None:
        ch = ClickHouse(
            host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )
    rows = ch.client.execute(
        f"""
        SELECT quantile(0.05)(capital_usd), quantile(0.95)(capital_usd)
        FROM polymetl.wallet_features FINAL
        WHERE target_market_id = %(cid)s AND capital_usd > 0
        """,
        {"cid": priors["condition_id"]},
    )
    cap_floor, cap_cap = rows[0] if rows else (0.0, 0.0)
    if cap_cap <= cap_floor:
        # Degenerate distribution (e.g. all wallets equal). Use min/max
        # bounded sensibly; documented in EMPIRICAL_PRIORS.md.
        cap_floor, cap_cap = max(1.0, cap_floor), max(cap_floor + 1.0, cap_cap, 100.0)
    log.info(
        "empirical capital bounds for %s: floor=$%.0f cap=$%.0f",
        priors["condition_id"][:18], cap_floor, cap_cap,
    )

    pop = build_population(
        target_market_id=priors["condition_id"],
        yes_token_id=priors["yes_token_id"],
        consensus_mu=priors["signal_mu"],
        capital_scale=1.0,
        capital_floor_usd=float(cap_floor),
        capital_cap_usd=float(cap_cap),
        seed=seed, cache_path=cache_path, ch=ch,
    )
    return pop, priors
