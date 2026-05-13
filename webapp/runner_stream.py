"""Streaming wrapper around the v8 experiment runner.

Differences from `experiments.runner.run_experiment`:
  - accepts (slug, n_agents, n_ticks_override, persona_set) directly
    (no YAML), so a user can point it at an open / unresolved market
    without first authoring a config file.
  - derives priors on-the-fly via `agent.features.market.derive_priors`
    and writes the JSON the agent factory expects.
  - emits structured events via a callback (`on_event`) after every
    notable step: derive_priors_done, population_built, env_ready,
    seed_done, tick_started, agent_decision, tick_finished, settled,
    done, error.
  - keeps parquet/ClickHouse dual-write OFF by default — the web
    demo is for interactive observation, not for the canonical run
    log. Set `persist=True` to mirror the YAML-runner behavior.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from agent.decision import decide
from agent.factory import init_agents
from agent.features.market import derive_priors
from data.query.markets import get_market_meta
from data.store.config import get_settings
from environment.env import PolyEnv
from environment.seeders.from_clob_history import seed as seed_from_clob


log = logging.getLogger(__name__)


EventCallback = Callable[[str, dict], None]


def _ensure_priors_json(slug: str, data_dir: Path) -> dict:
    """Return priors dict; create `data/priors_<slug>.json` if absent."""
    path = data_dir / f"priors_{slug}.json"
    if path.exists():
        return json.loads(path.read_text())
    priors = derive_priors(slug)
    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(priors, indent=2, default=str))
    log.info("derived priors for live market %s -> %s", slug, path)
    return priors


def _market_snapshot_dict(sim) -> dict:
    return {
        "yes_mid": float(sim.yes_mid),
        "no_mid": float(sim.no_mid),
        "yes_mid_history": [float(x) for x in sim.yes_mid_history[-200:]],
        "n_agents": len(sim.agents),
        "n_actions": len(sim.actions_log),
        "n_fills": len(sim.fills_log),
    }


def run_stream(
    *,
    slug: str,
    n_agents: int,
    n_ticks_override: Optional[int],
    persona_set: str = "archetype",
    seed: int = 0,
    temperature: float = 0.0,
    on_event: EventCallback,
    cancel: Optional[threading.Event] = None,
    data_dir: Path = Path("data"),
) -> None:
    """Execute one simulation, streaming events through `on_event`.

    Raises only for fatal preflight errors (unknown slug, missing API
    key). Per-tick LLM failures are reported as 'agent_decision' events
    with non-empty `api_error` and the loop continues.
    """
    settings = get_settings()
    started_at = dt.datetime.utcnow()

    on_event("run_started", {
        "slug": slug, "n_agents": n_agents,
        "n_ticks_requested": n_ticks_override,
        "persona_set": persona_set,
        "started_at": started_at.isoformat() + "Z",
    })

    # 1. Resolve market (live or resolved).
    meta = get_market_meta(slug)
    if meta is None:
        on_event("error", {
            "where": "get_market_meta",
            "message": f"slug {slug!r} not in clob_markets; ingest gamma_api/clob_api first",
        })
        return
    on_event("market_resolved", {
        "slug": slug, "condition_id": meta["condition_id"],
        "question": meta["question"],
        "winning_idx": meta["winning_idx"],
        "is_live": meta["winning_idx"] < 0,
        "tick_size": meta["tick_size"],
        "taker_fee_bps": meta["taker_fee_bps"],
        "volume": meta["volume"],
    })

    # 2. Derive priors (or load cached).
    try:
        priors = _ensure_priors_json(slug, data_dir)
    except Exception as exc:        # noqa: BLE001
        on_event("error", {"where": "derive_priors", "message": str(exc)})
        return
    on_event("priors_ready", {
        "signal_mu": priors["signal_mu"],
        "n_ticks_priors": priors["n_ticks"],
        "tick_size": priors["tick_size"],
        "taker_fee_bps": priors["taker_fee_bps"],
        "bootstrap_source": priors["bootstrap"]["source"],
    })

    # 3. Init agents.
    pop, _ = init_agents(
        slug, persona_set=persona_set, n_agents=n_agents, seed=seed,
    )
    if not pop:
        on_event("error", {
            "where": "init_agents",
            "message": "empty population; calibrated path requires "
                       "wallet_features rows for this market",
        })
        return
    on_event("population_built", {
        "n_agents": len(pop),
        "agents": [
            {
                "agent_id": i,
                "persona_type": a.persona_type,
                "capital_initial": float(a.capital_initial),
                "private_signal_mu": float(a.private_signal_mu),
                "profile_excerpt": (a.profile_text or "")[:180],
            }
            for i, a in enumerate(pop)
        ],
    })

    # 4. Build env + seed.
    n_ticks = int(n_ticks_override) if n_ticks_override else priors["n_ticks"]
    env = PolyEnv(
        market_meta=meta, population=pop,
        n_ticks=n_ticks, taker_fee_bps=priors["taker_fee_bps"],
        observer="quote_only",
    )
    obs = env.reset(seed=seed)
    try:
        seed_from_clob(env.state, priors)
    except Exception as exc:        # noqa: BLE001
        on_event("warn", {"where": "seed_from_clob", "message": str(exc)})
    sim = env.state
    on_event("env_ready", {
        "n_ticks": n_ticks,
        "yes_mid_post_seed": float(sim.yes_mid),
        **_market_snapshot_dict(sim),
    })

    # 5. LLM loop — events fire as soon as each decision lands.
    if not settings.DEEPSEEK_API_KEY:
        on_event("error", {
            "where": "preflight_llm",
            "message": "POLYMETL_DEEPSEEK_API_KEY not set; live demo requires it",
        })
        return

    model = settings.DEEPSEEK_MODEL
    for tick in range(n_ticks):
        if cancel is not None and cancel.is_set():
            on_event("cancelled", {"tick": tick})
            return
        tick_started = time.time()
        on_event("tick_started", {
            "tick": tick, "total": n_ticks,
            "yes_mid": float(sim.yes_mid),
        })

        # Sequential dispatch — streaming a real-time UI works much
        # better with predictable per-agent event ordering than the
        # 16-way thread pool used in the headless runner.
        actions: dict = {}
        for aid in obs:
            if cancel is not None and cancel.is_set():
                on_event("cancelled", {"tick": tick, "agent_id": aid})
                return
            market_snap, agent_snap = obs[aid]
            agent = next(a for a in sim.agents if a.agent_id == aid)
            t0 = time.time()
            try:
                decision = decide(
                    persona=agent.persona,
                    question=meta["question"],
                    description=meta.get("description", ""),
                    end_date=meta.get("end_date_iso", ""),
                    market=market_snap, agent=agent_snap,
                    api_key=settings.DEEPSEEK_API_KEY,
                    base_url=settings.DEEPSEEK_BASE_URL,
                    model=model,
                    tick_size=priors["tick_size"],
                    temperature=temperature,
                    timeout=settings.DEEPSEEK_TIMEOUT,
                    max_attempts=3,
                )
            except Exception as exc:        # noqa: BLE001
                on_event("agent_decision_error", {
                    "tick": tick, "agent_id": aid, "message": str(exc),
                })
                continue
            actions[aid] = decision
            on_event("agent_decision", {
                "tick": tick, "agent_id": aid,
                "persona_type": agent.persona.persona_type,
                "order_type": decision.order_type,
                "outcome": decision.outcome,
                "side": decision.side,
                "price": float(decision.price),
                "size_usd": float(decision.size_usd),
                "reasoning": (decision.reasoning or "").strip()[:400],
                "api_latency_ms": int(decision.api_latency_ms),
                "api_error": decision.api_error or "",
                "elapsed_s": round(time.time() - t0, 2),
            })

        obs, info = env.step(actions)
        on_event("tick_finished", {
            "tick": tick, "n_fills": int(info["n_fills"]),
            "elapsed_s": round(time.time() - tick_started, 2),
            **_market_snapshot_dict(sim),
        })

    # 6. Settle (no-op for unresolved markets) + final summary.
    pnl = env.settle()
    on_event("settled", {
        "pnl": {int(k): float(v) for k, v in pnl.items()},
        "n_actions": len(sim.actions_log),
        "n_fills": len(sim.fills_log),
        "yes_mid_final": float(sim.yes_mid),
        "wall_seconds": round(
            (dt.datetime.utcnow() - started_at).total_seconds(), 1,
        ),
    })
    on_event("done", {"sim_id": sim.sim_id})
