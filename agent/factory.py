"""v8 — Single entry to build a calibrated agent population.

`init_agents(market_id, n_agents=None, persona_set='calibrated',
recipe=None) -> list[AgentInit]`

Composes:
  1. priors JSON (data/priors_<slug>.json)
  2. wallet_features rows for the market
  3. cached personas (data/wallet_personas.json)
  4. data.query.wallets.empirical_capital_bounds (p5/p95)
  5. private signal sigma derived per-agent

Output is consumed by `environment.env.PolyEnv` (Stage 3).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent.personas.calibrated import CACHE_PATH, load_cache
from data.query._ch import get_ch
from data.query import wallets as q_wallets
from data.store.clickhouse import ClickHouse
from data.store.config import get_settings


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentInit:
    """Spec to instantiate one simulator agent. v7-stable schema."""
    wallet_addr: str
    persona_type: str            # "Calibrated"
    capital_initial: float
    profile_text: str
    private_signal_mu: float
    private_signal_sigma: float
    risk_aversion: float
    # Source features for SERD baseline benchmark (paper Table 5):
    src_tx_count: int
    src_maker_ratio: float
    src_avg_position_usd: float
    src_asset_diversity: int


def derive_signal_sigma(
    past_accuracy: float, scale: Optional[float] = None,
    floor: Optional[float] = None, cap: Optional[float] = None,
) -> float:
    """Higher empirical accuracy → tighter prior. Bounds enforced.

    Defaults from `Settings.SIGMA_*`. Marked v9 for full empirical
    replacement (pooled-sample p10/p90 of `1-past_accuracy`).
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
    """Truncated normal in (0.01, 0.99). Falls back to `mu` clamped if
    64 draws keep escaping the truncation bounds."""
    for _ in range(64):
        s = rng.gauss(mu, sigma)
        if 0.01 < s < 0.99:
            return s
    return max(0.01, min(0.99, mu))


def load_priors(slug: str, data_dir: Path = Path("data")) -> dict:
    """Load `data/priors_<slug>.json` produced by features.market."""
    path = data_dir / f"priors_{slug}.json"
    if not path.exists():
        raise SystemExit(
            f"priors not found at {path}; run "
            f"`python -m agent.features.market --slug {slug}` first"
        )
    return json.loads(path.read_text())


def _maybe_wire_archetype_paths(
    priors: dict, clustering_dir: Path = Path("data/clustering"),
) -> None:
    """v13 (Fix 7): if a cutoff-conditioned cluster table exists for
    this market's open, export ``POLYMETL_WALLET_CLUSTERS`` and
    ``POLYMETL_CLUSTER_PROFILES`` so ``agent.personas.archetype`` picks
    it up. No-op if the cutoff-suffixed files aren't on disk."""
    open_ts = priors.get("market_open_ts")
    if open_ts is None:
        return
    suffix = dt.datetime.utcfromtimestamp(int(open_ts)).strftime("%Y%m%dT%H%M%SZ")
    wc = clustering_dir / f"wallet_clusters_{suffix}.parquet"
    cp = clustering_dir / f"cluster_profiles_{suffix}.json"
    if wc.exists() and cp.exists():
        os.environ["POLYMETL_WALLET_CLUSTERS"] = str(wc)
        os.environ["POLYMETL_CLUSTER_PROFILES"] = str(cp)
        log.info("archetype: using cutoff-conditioned cluster tables %s / %s",
                 wc.name, cp.name)
    else:
        log.info(
            "archetype: no cutoff-conditioned cluster table at %s; "
            "falling back to legacy non-suffixed files",
            wc.name,
        )


def init_agents(
    slug: str,
    *,
    persona_set: str = "calibrated",
    n_agents: Optional[int] = None,
    seed: int = 0,
    cache_path: Path = CACHE_PATH,
    data_dir: Path = Path("data"),
    ch: Optional[ClickHouse] = None,
) -> tuple[list[AgentInit], dict]:
    """Build the agent population for `slug`. Returns
    `(agents, priors_dict)`.

    `persona_set='calibrated'` (default) reads wallet_features +
    cached personas. `persona_set='hand_coded'` is reserved for v9
    (currently raises NotImplementedError because the library
    registry is empty).

    `n_agents=None` keeps every wallet that has a cached persona
    (v7 default). Truncating to a smaller count uses deterministic
    seed-based shuffle.
    """
    if persona_set == "archetype":
        return _init_agents_archetype(
            slug=slug, n_agents=n_agents or 30, seed=seed,
            data_dir=data_dir, ch=ch,
        )
    if persona_set in ("marginal_random", "uniform_random"):
        return _init_agents_random_baseline(
            slug=slug, n_agents=n_agents or 30, seed=seed,
            data_dir=data_dir, ch=ch, variant=persona_set,
        )
    if persona_set not in ("calibrated", "no_signal"):
        raise NotImplementedError(
            f"persona_set={persona_set!r}; supported: 'calibrated', "
            f"'archetype', 'marginal_random', 'uniform_random', "
            f"'no_signal'."
        )
    # 'calibrated' and 'no_signal' share the body below; the latter
    # zeroes signals at the end (used by the v10 ablation).

    priors = load_priors(slug, data_dir=data_dir)
    ch = get_ch(ch)

    cap_floor, cap_cap = q_wallets.empirical_capital_bounds(
        priors["condition_id"], ch=ch,
    )
    if cap_cap <= cap_floor:
        cap_floor, cap_cap = max(1.0, cap_floor), max(cap_floor + 1.0, cap_cap, 100.0)
    log.info(
        "empirical capital bounds for %s: floor=$%.0f cap=$%.0f",
        priors["condition_id"][:18], cap_floor, cap_cap,
    )

    feature_rows = ch.fetch_wallet_features(priors["condition_id"])
    if not feature_rows:
        log.warning("no wallet_features rows for %s",
                    priors["condition_id"])
        return [], priors
    cache = load_cache(cache_path).get(priors["condition_id"], {})

    consensus_mu = float(priors["signal_mu"])
    rng = random.Random(seed)
    population: list[AgentInit] = []
    for r in feature_rows:
        wallet, capital_usd, tx_count, maker_ratio, avg_pos, \
            asset_diversity, avg_holding_h, past_accuracy, n_resolved_prior = r
        cached = cache.get(wallet)
        if not cached or not cached.get("ok"):
            log.warning("no cached profile for %s — skipped", wallet[:10])
            continue

        capital = max(cap_floor, min(cap_cap, float(capital_usd)))
        sigma = derive_signal_sigma(float(past_accuracy))
        signal = draw_private_signal(consensus_mu, sigma, rng)

        population.append(AgentInit(
            wallet_addr=wallet,
            persona_type="Calibrated",
            capital_initial=capital,
            profile_text=cached["profile_text"],
            private_signal_mu=signal,
            private_signal_sigma=sigma,
            risk_aversion=0.5,
            src_tx_count=int(tx_count),
            src_maker_ratio=float(maker_ratio),
            src_avg_position_usd=float(avg_pos),
            src_asset_diversity=int(asset_diversity),
        ))

    if n_agents is not None and n_agents < len(population):
        rng.shuffle(population)
        population = population[:n_agents]

    # v10 ablation: blank out private signal for the 'no_signal' variant.
    if persona_set == "no_signal":
        population = [
            AgentInit(
                wallet_addr=a.wallet_addr, persona_type="NoSignal",
                capital_initial=a.capital_initial,
                profile_text=a.profile_text,
                private_signal_mu=0.5, private_signal_sigma=0.5,
                risk_aversion=a.risk_aversion,
                src_tx_count=a.src_tx_count,
                src_maker_ratio=a.src_maker_ratio,
                src_avg_position_usd=a.src_avg_position_usd,
                src_asset_diversity=a.src_asset_diversity,
            )
            for a in population
        ]

    log.info(
        "init_agents(%s, %s): %d agents (capital $%.0f..$%.0f, "
        "mu %.2f..%.2f, consensus_mu=%.3f)",
        slug, persona_set, len(population),
        min((a.capital_initial for a in population), default=0.0),
        max((a.capital_initial for a in population), default=0.0),
        min((a.private_signal_mu for a in population), default=0.0),
        max((a.private_signal_mu for a in population), default=0.0),
        consensus_mu,
    )
    return population, priors


def _init_agents_archetype(
    *, slug: str, n_agents: int, seed: int,
    data_dir: Path, ch: Optional[ClickHouse],
) -> tuple[list[AgentInit], dict]:
    """v10: build a population by sampling K-means archetypes from the
    1.19M-wallet empirical distribution. No live LLM persona call:
    profile_text is the wallet's raw feature values, the trader LLM
    infers style at decision time."""
    from agent.personas import archetype as _archetype

    priors = load_priors(slug, data_dir=data_dir)
    ch = get_ch(ch)

    # v13 (audit L-1, Fix 7): if a cutoff-conditioned cluster table
    # exists for this market's open, prefer it over the legacy
    # non-suffixed files. We point the archetype sampler at the new
    # paths via environment variables so existing callers keep
    # working (env-var override is module-level).
    _maybe_wire_archetype_paths(priors)
    _archetype.reset_caches()
    build_archetype_population = _archetype.build_archetype_population
    # v10.1: archetype path NO LONGER clamps capital to the target market's
    # p5/p95 wallet_features distribution — doing so was inconsistent with
    # the profile_text (which states the wallet's real $XXX notional) and
    # caused exp004 to be unusually quiet. Use the wallet's REAL total
    # notional as starting cash, bounded only by a $10 minimum to avoid
    # degenerate zero-capital agents.
    rng = random.Random(seed)
    consensus_mu = float(priors["signal_mu"])
    pop = build_archetype_population(n_agents=n_agents, seed=seed)
    out: list[AgentInit] = []
    for i, a in enumerate(pop):
        f = a["features"]
        capital = max(10.0, float(f["total_notional"]))
        past_acc = f.get("past_accuracy")
        past_acc = 0.5 if (past_acc is None or
                            (isinstance(past_acc, float) and math.isnan(past_acc))) \
                       else float(past_acc)
        sigma = derive_signal_sigma(past_acc)
        signal = draw_private_signal(consensus_mu, sigma, rng)
        out.append(AgentInit(
            wallet_addr=a["wallet_addr"],
            persona_type=f"Archetype-C{a['cluster_id']}",
            capital_initial=capital,
            profile_text=a["profile_text"],
            private_signal_mu=signal,
            private_signal_sigma=sigma,
            risk_aversion=0.5,
            src_tx_count=int(f["tx_count"]),
            src_maker_ratio=0.0,
            src_avg_position_usd=float(f["total_notional"]) / max(int(f["tx_count"]), 1),
            src_asset_diversity=int(f["n_markets"]),
        ))

    by_cluster = {}
    for a in out:
        by_cluster.setdefault(a.persona_type, 0)
        by_cluster[a.persona_type] += 1
    log.info(
        "init_agents(%s, persona_set=archetype): %d agents, cluster mix=%s, "
        "capital $%.0f..$%.0f, mu %.2f..%.2f",
        slug, len(out), by_cluster,
        min((a.capital_initial for a in out), default=0.0),
        max((a.capital_initial for a in out), default=0.0),
        min((a.private_signal_mu for a in out), default=0.0),
        max((a.private_signal_mu for a in out), default=0.0),
    )
    return out, priors


def _init_agents_random_baseline(
    *, slug: str, n_agents: int, seed: int,
    data_dir: Path, ch: Optional[ClickHouse], variant: str,
) -> tuple[list[AgentInit], dict]:
    """v13: B3 baselines — wallets sampled either uniformly or
    stratified to match population marginals. Same AgentInit shape as
    the archetype path."""
    from agent.personas.random_baseline import (
        build_marginal_population, build_uniform_population,
    )

    priors = load_priors(slug, data_dir=data_dir)
    ch = get_ch(ch)
    rng = random.Random(seed)
    consensus_mu = float(priors["signal_mu"])

    if variant == "marginal_random":
        pop = build_marginal_population(n_agents=n_agents, seed=seed)
    elif variant == "uniform_random":
        pop = build_uniform_population(n_agents=n_agents, seed=seed)
    else:  # pragma: no cover - guarded upstream
        raise ValueError(f"unknown random-baseline variant {variant!r}")

    out: list[AgentInit] = []
    for a in pop:
        f = a["features"]
        capital = max(10.0, float(f["total_notional"]))
        past_acc = f.get("past_accuracy")
        past_acc = 0.5 if (past_acc is None or
                           (isinstance(past_acc, float) and math.isnan(past_acc))) \
                      else float(past_acc)
        sigma = derive_signal_sigma(past_acc)
        signal = draw_private_signal(consensus_mu, sigma, rng)
        persona_label = ("Marginal" if variant == "marginal_random"
                         else "Uniform")
        out.append(AgentInit(
            wallet_addr=a["wallet_addr"],
            persona_type=f"{persona_label}-C{a.get('cluster_id', -1)}",
            capital_initial=capital,
            profile_text=a["profile_text"],
            private_signal_mu=signal,
            private_signal_sigma=sigma,
            risk_aversion=0.5,
            src_tx_count=int(f["tx_count"]),
            src_maker_ratio=0.0,
            src_avg_position_usd=float(f["total_notional"])
                / max(int(f["tx_count"]), 1),
            src_asset_diversity=int(f["n_markets"]),
        ))
    log.info(
        "init_agents(%s, persona_set=%s): %d agents, "
        "capital $%.0f..$%.0f, mu %.2f..%.2f",
        slug, variant, len(out),
        min((a.capital_initial for a in out), default=0.0),
        max((a.capital_initial for a in out), default=0.0),
        min((a.private_signal_mu for a in out), default=0.0),
        max((a.private_signal_mu for a in out), default=0.0),
    )
    return out, priors


# math import for archetype path
import math


def main() -> None:
    """CLI: `python -m agent.factory --slug <slug> --dry-run`."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="print population summary, don't return")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    pop, priors = init_agents(slug=args.slug)
    print(f"\nPopulation summary for {args.slug}:")
    print(f"  n_agents:    {len(pop)}")
    print(f"  signal_mu:   {priors['signal_mu']:.3f}")
    print(f"  n_ticks:     {priors['n_ticks']}")
    print(f"  tick_size:   {priors['tick_size']}")
    if pop:
        a = pop[0]
        print(f"\n  Sample agent (wallet={a.wallet_addr[:10]}):")
        print(f"    capital_initial: ${a.capital_initial:,.0f}")
        print(f"    private signal:  μ={a.private_signal_mu:.3f}, σ={a.private_signal_sigma:.3f}")
        print(f"    profile (first 200 chars):")
        print(f"      {a.profile_text[:200]}")


if __name__ == "__main__":
    main()
