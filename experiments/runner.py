"""v8 — YAML-driven experiment runner.

One entry point: `run_experiment(config_path, output_dir='output')`
returns the `exp_id` and writes:
  output/<exp_id>/meta.json
  output/<exp_id>/raw/{agent_actions,fills,positions,personas}.parquet
  output/<exp_id>/raw/llm_calls.jsonl  (if dry_run=False)
  output/<exp_id>/analysis/  (post-hoc, after Gym loop)
  output/<exp_id>/figure/    (Stage 7 plots)

The runner composes:
  data.query.markets.get_market_meta
  agent.factory.init_agents             — calibrated population
  environment.env.PolyEnv               — Gym loop
  environment.seeders.from_clob_history.seed
  experiments.parquet_sink.dump_simulation
  experiments.analysis.serd.analyze_sim (after sim)

It does NOT touch SQL directly.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import yaml

from agent.decision import decide
from agent.decision.types import AgentSnapshot, MarketSnapshot
from agent.factory import init_agents
from agent.personas.persona import Persona
from data.query.markets import get_market_meta
from data.store.config import get_settings
from environment.env import PolyEnv
from environment.seeders.from_clob_history import seed as seed_from_clob
from environment.seeders.from_holders import seed as seed_from_holders
from experiments.config import ExperimentConfig, parse_config
from experiments.parquet_sink import (
    PERSONA_COLUMNS, append_llm_call, dump_simulation,
)
from experiments.postprocess import run_postprocess


log = logging.getLogger(__name__)


# ============================================================
# v13 (B6) — synthetic external-news shock
# ============================================================


def apply_shock_if_due(sim, tick: int, shock_cfg) -> int:
    """Inject a synthetic memory entry into every agent if ``tick``
    matches ``shock_cfg.tick``. Returns the number of agents touched
    (0 means no shock fired). Idempotent: safe to call once per tick.

    The injection mutates ``agent.memory`` directly so the next call
    to ``observe()`` packs the synthetic entry into
    ``AgentSnapshot.recent_decisions``."""
    if shock_cfg is None:
        return 0
    if int(tick) != int(shock_cfg.tick):
        return 0
    entry = {
        "tick": int(shock_cfg.tick),
        "action": "EXTERNAL_NEWS",
        "outcome": "",
        "side": "",
        "price": 0.0,
        "size_usd": 0.0,
        "fills": 0,
        "yes_mid_after": float(getattr(sim, "yes_mid", 0.5)),
        "reasoning": str(shock_cfg.payload.text)[:240],
        "kind": shock_cfg.kind,
    }
    n = 0
    for a in sim.agents:
        if getattr(a, "memory", None) is None:
            a.memory = []
        a.memory.append(entry)
        n += 1
    log.info("shock fired at tick=%d (kind=%s, n_agents=%d): %s",
             tick, shock_cfg.kind, n, entry["reasoning"][:80])
    return n


# ============================================================
# exp_id derivation
# ============================================================


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:        # noqa: BLE001
        return "no-git"


def _config_hash(config: ExperimentConfig) -> str:
    """Stable hash of the resolved config dict."""
    payload = json.dumps(
        config.model_dump(), sort_keys=True, default=str,
    ).encode()
    return hashlib.sha256(payload).hexdigest()[:8]


def compute_exp_id(config: ExperimentConfig, *, now: Optional[dt.datetime] = None,
                   git_sha: Optional[str] = None) -> str:
    """`<utc_timestamp>-<name>-<git_sha8>-<cfg_hash8>`.

    Deterministic given (config, git_sha, timestamp). The timestamp
    component is intentional — repeated runs of the same config get
    distinct exp_ids (one experiment per attempt).
    """
    now = now or dt.datetime.utcnow()
    sha = (git_sha or _git_sha())[:8]
    cfg_h = _config_hash(config)
    ts = now.strftime("%Y%m%dT%H%M%S")
    return f"{ts}-{config.name}-{sha}-{cfg_h}"


# ============================================================
# Config loading
# ============================================================


def load_config(yaml_path: str | Path) -> ExperimentConfig:
    """Load + parse a YAML config file. Defaults from ExperimentConfig."""
    p = Path(yaml_path)
    data = yaml.safe_load(p.read_text()) or {}
    return parse_config(data)


# ============================================================
# meta.json writer
# ============================================================


def write_meta(out_dir: Path, exp_id: str, config: ExperimentConfig,
               started_at: dt.datetime, ended_at: Optional[dt.datetime],
               sim_id: Optional[str], n_agents: int, n_ticks: int,
               git_sha: str, priors_summary: dict | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "exp_id": exp_id,
        "started_at": started_at.isoformat() + "Z",
        "ended_at": ended_at.isoformat() + "Z" if ended_at else None,
        "git_sha": git_sha,
        "config": config.model_dump(),
        "sim_id": sim_id,
        "n_agents": n_agents,
        "n_ticks": n_ticks,
        "priors_summary": priors_summary or {},
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))


# ============================================================
# Per-tick decision dispatch (v9.3 — concurrent)
# ============================================================


def _resolve_concurrency(requested: Optional[int], n_agents: int) -> int:
    """Translate config.llm.concurrency → effective worker count.

    None → min(n_agents, 16); 0 or 1 → serial; else clamp to n_agents.
    """
    if requested is None:
        return max(1, min(n_agents, 16))
    if requested <= 1:
        return 1
    return min(int(requested), n_agents)


def _decide_all_agents(
    *, sim, obs: dict, meta: dict, tick: int, n_ticks_eff: int,
    api_key: str, base_url: str, model: str, tick_size: float,
    temperature: float, timeout_s: float, max_attempts: int,
    concurrency: int, out_dir: Path,
):
    """Run `decide()` for every agent in `obs` and return the
    `{agent_id: Decision}` dict the env expects.

    Concurrency: 1 = serial (legacy); >1 = thread pool. Within a tick
    all agents see the SAME pre-built obs, so order doesn't affect
    each agent's input. Engine still processes them in the random
    order the env shuffled (in `env.step`)."""

    def _one(aid: int):
        market, agent_state = obs[aid]
        agent = next(a for a in sim.agents if a.agent_id == aid)
        decision = decide(
            persona=agent.persona,
            question=meta["question"],
            description=meta.get("description", ""),
            end_date=meta.get("end_date_iso", ""),
            market=market, agent=agent_state,
            api_key=api_key, base_url=base_url, model=model,
            tick_size=tick_size,
            temperature=temperature,
            timeout=timeout_s,
            max_attempts=max_attempts,
        )
        append_llm_call(
            out_dir, sim.sim_id, tick, aid,
            system_prompt="(reproducible from persona + clob_system.j2)",
            user_prompt="(reproducible from MarketSnapshot + AgentSnapshot)",
            response=decision.raw_response,
        )
        return aid, decision

    actions: dict = {}
    if concurrency <= 1:
        for aid in obs:
            aid_, dec = _one(aid)
            actions[aid_] = dec
        return actions

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=concurrency,
        thread_name_prefix=f"tick{tick}",
    ) as pool:
        for aid_, dec in pool.map(_one, list(obs)):
            actions[aid_] = dec
    return actions


# ============================================================
# Top-level orchestration
# ============================================================


def run_experiment(
    config_path: str | Path,
    *,
    output_dir: str | Path = "output",
    dry_run: bool = False,
) -> str:
    """Execute one experiment per `config_path`. Returns exp_id."""
    config = load_config(config_path)
    git_sha = _git_sha()
    exp_id = compute_exp_id(config, git_sha=git_sha)
    out = Path(output_dir) / exp_id
    started_at = dt.datetime.utcnow()
    settings = get_settings()
    log.info("=" * 60)
    log.info("Experiment %s (config=%s, git=%s)", exp_id, config.name, git_sha[:8])

    # 1. Resolve market + features + population
    meta = get_market_meta(config.market.slug)
    if meta is None:
        raise SystemExit(
            f"slug {config.market.slug!r} not in clob_markets; "
            f"ingest data.sources.gamma_api + clob_api first"
        )
    pop, priors = init_agents(
        config.market.slug,
        persona_set=config.agent.population,
        n_agents=config.agent.n_agents,
        seed=config.agent.seed,
    )
    if not pop:
        raise SystemExit(
            "calibrated population is empty; run wallet_features + "
            "persona generation first (see docs/REPRODUCE.md)"
        )

    n_ticks = priors["n_ticks"]
    fee_bps = (config.environment.fees_override_bps
               if config.environment.fees_override_bps is not None
               else priors["taker_fee_bps"])
    log.info("  population: %d agents (slug=%s)", len(pop), config.market.slug)
    log.info("  priors:     n_ticks=%d, signal_mu=%.3f, fee_bps=%.2f",
             n_ticks, priors["signal_mu"], fee_bps)

    # 2. Build env + seed liquidity
    env = PolyEnv(
        market_meta=meta, population=pop,
        n_ticks=n_ticks, taker_fee_bps=fee_bps,
        observer=config.environment.observer,
    )
    obs = env.reset(seed=config.agent.seed)
    if config.environment.seeder == "from_clob_history":
        seed_from_clob(env.state, priors)
    elif config.environment.seeder == "from_holders":
        seed_from_holders(env.state, priors["condition_id"])
    sim = env.state
    log.info("  env: yes_mid post-seed = %.3f", sim.yes_mid)

    if dry_run:
        # Write meta + persona parquet so output/<exp_id>/ exists,
        # but skip the LLM loop and analysis.
        persona_rows = [
            (sim.sim_id, a.agent_id, a.persona.persona_type,
             a.persona.risk_aversion, a.persona.capital_initial,
             a.persona.profile_text)
            for a in sim.agents
        ]
        dump_simulation(sim, out, compression=config.output.parquet_compression,
                        persona_rows=persona_rows)
        write_meta(
            out, exp_id, config, started_at, dt.datetime.utcnow(),
            sim_id=sim.sim_id, n_agents=len(pop), n_ticks=n_ticks,
            git_sha=git_sha, priors_summary={
                "signal_mu": priors["signal_mu"],
                "n_ticks": n_ticks,
                "tick_size": priors["tick_size"],
                "taker_fee_bps": priors["taker_fee_bps"],
                "bootstrap_source": priors["bootstrap"]["source"],
            },
        )
        # Post-process even in dry-run: analysis/* + figure/* readable.
        priors_summary = {
            "signal_mu": priors["signal_mu"],
            "n_ticks": n_ticks,
            "tick_size": priors["tick_size"],
            "taker_fee_bps": priors["taker_fee_bps"],
            "bootstrap_source": priors["bootstrap"]["source"],
            "dry_run": True,
        }
        pp_ch = None
        if config.output.dual_write_clickhouse:
            from data.store.clickhouse import ClickHouse
            pp_ch = ClickHouse(
                host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
                user=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD,
                database=settings.CLICKHOUSE_DATABASE,
            )
        try:
            run_postprocess(
                out_dir=out, slug=config.market.slug, sim=sim, pnl={},
                priors_summary=priors_summary,
                compression=config.output.parquet_compression,
                ch=pp_ch, want_serd=False,    # no fills yet → skip SERD
            )
        except Exception as exc:        # noqa: BLE001
            log.warning("dry-run postprocess failed: %s", exc)
        try:
            from viz.report import build_report
            build_report(out)
        except Exception as exc:        # noqa: BLE001
            log.warning("HTML report failed: %s", exc)
        log.info("[dry-run] wrote %s/{meta.json, raw/, analysis/, figure/, report.html}",
                 out)
        return exp_id

    # 3. Run Gym loop (LIVE — needs DEEPSEEK_API_KEY)
    if not settings.DEEPSEEK_API_KEY:
        raise SystemExit(
            "POLYMETL_DEEPSEEK_API_KEY required for live run; "
            "use --dry-run for a structural preview"
        )

    model = config.llm.model or settings.DEEPSEEK_MODEL
    concurrency = _resolve_concurrency(config.llm.concurrency, len(pop))
    log.info("  per-tick LLM concurrency: %d (config=%s, n_agents=%d)",
             concurrency, config.llm.concurrency, len(pop))
    for tick in range(n_ticks):
        tick_started = time.time()
        actions = _decide_all_agents(
            sim=sim, obs=obs, meta=meta,
            tick=tick, n_ticks_eff=n_ticks,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            model=model, tick_size=priors["tick_size"],
            temperature=config.llm.temperature,
            timeout_s=config.llm.timeout_s,
            max_attempts=config.llm.retry.max_attempts,
            concurrency=concurrency, out_dir=out,
        )
        obs, info = env.step(actions)
        # v13 (B6): fire external-news shock at the configured tick.
        # Injecting AFTER env.step means agents see the synthetic
        # entry in their next-tick prompt's recent_decisions block.
        apply_shock_if_due(sim, tick, config.experiment.shock)
        # Re-pack observations so the next tick's obs sees the shock.
        if (config.experiment.shock is not None
                and tick == config.experiment.shock.tick):
            obs = env._observations()  # noqa: SLF001
        log.info("  tick=%d/%d fills=%d yes_mid=%.3f (%.1fs)",
                 tick + 1, n_ticks, info["n_fills"], sim.yes_mid,
                 time.time() - tick_started)

    pnl = env.settle()
    ended_at = dt.datetime.utcnow()
    log.info("  sim complete: %d agents, %d actions, %d fills",
             len(pop), len(sim.actions_log), len(sim.fills_log))

    # 4. Persist parquet (raw)
    persona_rows = [
        (sim.sim_id, a.agent_id, a.persona.persona_type,
         a.persona.risk_aversion, a.persona.capital_initial,
         a.persona.profile_text)
        for a in sim.agents
    ]
    dumped = dump_simulation(
        sim, out, compression=config.output.parquet_compression,
        persona_rows=persona_rows,
    )
    log.info("  parquet: %s", dumped)

    # 5. Optional ClickHouse dual-write (preserves SERD SQL path)
    if config.output.dual_write_clickhouse:
        from data.store.clickhouse import ClickHouse
        ch = ClickHouse(
            host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )
        ch.ensure_sim_schema()
        ch.insert_personas(persona_rows)
        ch.insert_actions(sim.actions_log)
        ch.insert_fills(sim.fills_log)
        ch.insert_positions(sim.positions_log)
        ch.insert_simulation((
            sim.sim_id, sim.market_id, sim.market_slug,
            "CLOB", sim.taker_fee_bps,
            "Calibrated", len(sim.agents), n_ticks,
            started_at, ended_at, sim.yes_mid,
            sim.market_resolved_yes,
            json.dumps({"exp_id": exp_id, "config_name": config.name}),
        ))
        log.info("  ClickHouse dual-write: sim_id=%s", sim.sim_id)

    # 6. Post-process: analysis/* + figure/* + summary.json
    priors_summary = {
        "signal_mu": priors["signal_mu"],
        "n_ticks": n_ticks,
        "tick_size": priors["tick_size"],
        "taker_fee_bps": priors["taker_fee_bps"],
        "bootstrap_source": priors["bootstrap"]["source"],
        "pnl_summary": {
            "n_agents": len(pnl),
            "mean_pnl": (sum(pnl.values()) / len(pnl)) if pnl else 0.0,
        },
    }
    pp_ch = None
    if config.output.dual_write_clickhouse:
        from data.store.clickhouse import ClickHouse
        pp_ch = ClickHouse(
            host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )
    try:
        run_postprocess(
            out_dir=out, slug=config.market.slug, sim=sim, pnl=pnl,
            priors_summary=priors_summary,
            compression=config.output.parquet_compression,
            ch=pp_ch, want_serd=True,
        )
    except Exception as exc:        # noqa: BLE001
        log.warning("post-process step failed: %s — meta.json + raw/ still written", exc)

    # 7. meta.json
    write_meta(
        out, exp_id, config, started_at, ended_at,
        sim_id=sim.sim_id, n_agents=len(pop), n_ticks=n_ticks,
        git_sha=git_sha, priors_summary=priors_summary,
    )

    # 8. HTML report (reads meta.json + parquet + figures we just wrote).
    try:
        from viz.report import build_report
        build_report(out)
    except Exception as exc:        # noqa: BLE001
        log.warning("HTML report failed: %s", exc)

    log.info("Experiment %s done; artifacts in %s", exp_id, out)
    return exp_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="path to experiments/configs/*.yaml")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    exp_id = run_experiment(
        args.config, output_dir=args.output_dir, dry_run=args.dry_run,
    )
    print(f"\nexp_id: {exp_id}")


if __name__ == "__main__":
    main()
