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
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import Callable, Optional

from agent.decision import Decision, decide
from agent.factory import init_agents, build_synthetic_population
from agent.features.market import derive_priors
from agent.loop import (
    AgentLoopContext,
    AgentLoopObserver,
    CompositeAgentLoopObserver,
)
from agent.multi_agent.forum_adapter import ForumInteractionAdapter
from agent.multi_agent.protocol import (
    DEFAULT_INTERACTION_BUDGET,
    InteractionBudget,
    InteractionTranscript,
)
from agent.multi_agent.scheduler import (
    AgentScheduler,
    SequentialAgentScheduler,
    validate_schedule,
)
from data.query.markets import get_market_meta
from data.store.config import get_settings
from environment.env import PolyEnv
from environment.seeders.from_clob_history import seed as seed_from_clob
from evaluation.agent_loop import (
    AgentEvaluationSession,
    AgentLoopEvaluationObserver,
)
from evaluation.metrics.macro import compute_tick_metrics
from evaluation.metrics.micro import snapshot_all
from observability import create_observability

try:
    from .checkpoint import load_checkpoint, rng_from_state, save_checkpoint
except ImportError:  # Direct execution from sim/runner.
    from checkpoint import load_checkpoint, rng_from_state, save_checkpoint


log = logging.getLogger(__name__)


EventCallback = Callable[[str, dict], None]

# Global LLM concurrency limiter. The current tick loop is sequential (one
# agent at a time), but if it is later parallelized (e.g. thread pool), this
# semaphore caps the number of simultaneous in-flight LLM calls so provider
# rate limits are not overwhelmed. Default 4.
_LLM_SEMAPHORE = threading.Semaphore(4)


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


def _public_prompt_metadata(decision: Decision) -> list[dict]:
    """Expose reproducibility identity without duplicating prompt contents."""
    public = []
    for item in decision.prompt_metadata or []:
        clean = {key: value for key, value in item.items() if key != "variables"}
        clean["variable_names"] = item.get("variable_names", [])
        public.append(clean)
    return public


def _budget_hold_decision(
    *,
    total_tokens: int,
    token_budget: int,
    decision: Decision | None = None,
    decision_id: str = "",
) -> Decision:
    """Return a zero-cost HOLD after an agent exhausts its token budget.

    When ``decision`` is provided, retain its audit metadata and any belief
    or forum side effects from the just-completed call. Subsequent ticks pass
    no decision, so no provider call or token consumption occurs.
    """
    reason = f"token_budget_exceeded ({total_tokens}>={token_budget})"
    if decision is not None:
        return replace(
            decision,
            order_type="HOLD",
            size_usd=0.0,
            reasoning=reason,
            api_error="budget: token_budget_exceeded",
            decision_id=decision_id or decision.decision_id,
        )
    return Decision(
        order_type="HOLD",
        outcome="YES",
        side="BUY",
        price=0.5,
        size_usd=0.0,
        reasoning=reason,
        raw_response="",
        api_latency_ms=0,
        api_error="budget: token_budget_exceeded",
        decision_id=decision_id,
    )


def _emit_decision_scores(
    *,
    evaluation: AgentEvaluationSession,
    decision: Decision,
    tick: int,
    agent_id: int,
    tick_size: float,
    token_budget: int,
    total_tokens: int,
    lifecycle_events: list[dict],
    on_event: EventCallback,
) -> None:
    """Evaluate without risking the simulation's primary execution path."""
    try:
        scores = evaluation.score_decision(
            decision,
            tick=tick,
            agent_id=agent_id,
            tick_size=tick_size,
            token_budget=token_budget,
            total_tokens=total_tokens,
            lifecycle_events=lifecycle_events,
        )
        on_event("agent_scores", {
            "run_id": evaluation.run_id,
            "tick": tick,
            "agent_id": agent_id,
            "decision_id": decision.decision_id,
            "step_id": f"{decision.decision_id}:evaluate:0",
            "scores": [score.to_record() for score in scores],
        })
    except Exception as exc:  # noqa: BLE001 - eval is fail-open
        log.warning("Agent evaluation failed", exc_info=True)
        on_event("evaluation_error", {
            "scope": "decision",
            "tick": tick,
            "agent_id": agent_id,
            "decision_id": decision.decision_id,
            "message": str(exc),
        })


def _sync_evaluation_state(sim, evaluation: AgentEvaluationSession) -> None:
    """Persist only JSON/pickle-safe accumulator data for checkpoint resume."""
    sim.evaluation_schedules = [dict(item) for item in evaluation.schedules]
    sim.evaluation_beliefs = list(evaluation.beliefs)
    sim.evaluation_prompt_versions = sorted(evaluation.prompt_versions)


def _run_stream_impl(
    *,
    slug: str,
    n_agents: int,
    n_ticks_override: Optional[int],
    persona_set: str = "archetype",
    seed: int = 0,
    temperature: float = 0.0,
    on_event: EventCallback,
    cancel: Optional[threading.Event] = None,
    pause: Optional[threading.Event] = None,
    checkpoint_out: Optional[str] = None,
    data_dir: Path = Path("data"),
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    agent_loop_observer: AgentLoopObserver | None = None,
    agent_scheduler: AgentScheduler | None = None,
    interaction_budget: InteractionBudget = DEFAULT_INTERACTION_BUDGET,
) -> None:
    """Execute one simulation, streaming events through `on_event`.

    Raises only for fatal preflight errors (unknown slug, missing API
    key). Per-tick LLM failures are reported as 'agent_decision' events
    with non-empty `api_error` and the loop continues.

    If `pause` is set at a tick boundary and `checkpoint_out` is given,
    the run writes a checkpoint to that path, emits a `paused` event and
    returns cleanly (no `settled`/`done`). Resume later via `resume_stream`.

    `agent_loop_observer`, when supplied, receives lifecycle events for every
    provider-backed agent decision. It is not invoked for deterministic
    budget HOLDs, which remain visible through the normal runner event stream.
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

    # 3. Init agents. The calibrated/archetype/random persona sets need ingested
    # on-chain data (wallet_features / cluster_profiles.json). For an arbitrary
    # live market that data usually isn't present, so fall back to a synthetic,
    # data-free population (deterministic by seed) and warn — this lets ANY
    # market be simulated instead of hard-failing.
    pop = []
    try:
        pop, _ = init_agents(
            slug, persona_set=persona_set, n_agents=n_agents, seed=seed,
        )
    except Exception as exc:        # noqa: BLE001
        on_event("warn", {
            "where": "init_agents",
            "message": f"persona_set {persona_set!r} unavailable ({exc}); "
                       f"falling back to synthetic personas",
        })
    if not pop:
        pop = build_synthetic_population(priors, n_agents=n_agents, seed=seed)
        on_event("persona_fallback", {
            "requested": persona_set,
            "used": "synthetic",
            "n_agents": len(pop),
            "reason": "no ingested on-chain data for this market; "
                      "using synthetic (uncalibrated) personas",
        })
    if not pop:
        on_event("error", {
            "where": "init_agents",
            "message": "could not build any agent population",
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
    _api_key = api_key or settings.DEEPSEEK_API_KEY
    _base_url = base_url or settings.DEEPSEEK_BASE_URL
    _model = model or settings.DEEPSEEK_MODEL

    if not _api_key:
        on_event("error", {
            "where": "preflight_llm",
            "message": "LLM API key not set; configure provider in Settings or set POLYMETL_DEEPSEEK_API_KEY",
        })
        return
    prev_yes_mid: Optional[float] = float(sim.yes_mid)
    _run_tick_loop(
        env=env, obs=obs, meta=meta, priors=priors,
        n_ticks=n_ticks, start_tick=0,
        slug=slug, persona_set=persona_set, seed=seed,
        temperature=temperature, prev_yes_mid=prev_yes_mid,
        api_key=_api_key, base_url=_base_url, model=_model,
        settings=settings, on_event=on_event,
        cancel=cancel, pause=pause, checkpoint_out=checkpoint_out,
        started_at=started_at,
        agent_loop_observer=agent_loop_observer,
        agent_scheduler=agent_scheduler,
        interaction_budget=interaction_budget,
    )


def _resume_stream_impl(
    *,
    resume_checkpoint: str,
    on_event: EventCallback,
    cancel: Optional[threading.Event] = None,
    pause: Optional[threading.Event] = None,
    checkpoint_out: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    agent_loop_observer: AgentLoopObserver | None = None,
    agent_scheduler: AgentScheduler | None = None,
    interaction_budget: InteractionBudget = DEFAULT_INTERACTION_BUDGET,
) -> None:
    """Resume a previously paused run from a checkpoint pickle.

    Reconstructs the env around the pickled `Simulation` (mirroring the
    state restore in env.sensitivity_run: assign env.sim, env._tick,
    env._rng), then continues the tick loop from `next_tick`. The market
    and priors are taken from the checkpoint, so no re-derivation occurs
    and the resumed run reproduces the original from the pause point.
    """
    settings = get_settings()
    started_at = dt.datetime.utcnow()

    ckpt = load_checkpoint(resume_checkpoint)
    sim = ckpt["sim"]
    rng = rng_from_state(ckpt["rng_state"])
    next_tick = int(ckpt["next_tick"])
    n_ticks = int(ckpt["n_ticks"])
    meta = ckpt["market_meta"]
    priors = ckpt["priors"]
    slug = ckpt["slug"]
    persona_set = ckpt["persona_set"]
    seed = int(ckpt["seed"])
    temperature = float(ckpt["temperature"])
    prev_yes_mid = ckpt.get("prev_yes_mid")

    on_event("run_resumed", {
        "slug": slug, "resume_tick": next_tick, "n_ticks": n_ticks,
        "checkpoint": resume_checkpoint,
        "resumed_at": started_at.isoformat() + "Z",
    })

    # Rebuild env wrapping the restored sim. The constructor needs the
    # population only for reset(); we bypass reset() and inject state
    # directly (same pattern as env.sensitivity_run's restore block).
    env = PolyEnv(
        market_meta=meta, population=sim.agents,
        n_ticks=n_ticks, taker_fee_bps=priors["taker_fee_bps"],
        observer="quote_only",
    )
    env.sim = sim
    env._tick = next_tick
    env._rng = rng
    obs = env._observations()

    on_event("env_ready", {
        "n_ticks": n_ticks,
        "yes_mid_post_seed": float(sim.yes_mid),
        "resumed_from_tick": next_tick,
        **_market_snapshot_dict(sim),
    })

    _api_key = api_key or settings.DEEPSEEK_API_KEY
    _base_url = base_url or settings.DEEPSEEK_BASE_URL
    _model = model or settings.DEEPSEEK_MODEL
    if not _api_key:
        on_event("error", {
            "where": "preflight_llm",
            "message": "LLM API key not set; configure provider in Settings or set POLYMETL_DEEPSEEK_API_KEY",
        })
        return

    _run_tick_loop(
        env=env, obs=obs, meta=meta, priors=priors,
        n_ticks=n_ticks, start_tick=next_tick,
        slug=slug, persona_set=persona_set, seed=seed,
        temperature=temperature, prev_yes_mid=prev_yes_mid,
        api_key=_api_key, base_url=_base_url, model=_model,
        settings=settings, on_event=on_event,
        cancel=cancel, pause=pause, checkpoint_out=checkpoint_out,
        started_at=started_at,
        agent_loop_observer=agent_loop_observer,
        agent_scheduler=agent_scheduler,
        interaction_budget=interaction_budget,
    )


def _observed_agent_loop_observer(
    supplied: AgentLoopObserver | None,
    telemetry,
) -> AgentLoopObserver:
    if supplied is None:
        return telemetry.agent_loop_observer
    return CompositeAgentLoopObserver((supplied, telemetry.agent_loop_observer))


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
    pause: Optional[threading.Event] = None,
    checkpoint_out: Optional[str] = None,
    data_dir: Path = Path("data"),
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    agent_loop_observer: AgentLoopObserver | None = None,
) -> None:
    """Run a simulation with optional, fail-open observability."""
    session_id = f"poly:{uuid.uuid4()}"
    telemetry = create_observability(
        get_settings(),
        session_id=session_id,
        metadata={
            "mode": "fresh",
            "market_slug": slug,
            "n_agents": n_agents,
            "n_ticks_requested": n_ticks_override,
            "persona_set": persona_set,
            "seed": seed,
        },
    )

    def observed_event(kind: str, payload: dict) -> None:
        telemetry.on_runner_event(kind, payload)
        on_event(kind, payload)

    try:
        _run_stream_impl(
            slug=slug,
            n_agents=n_agents,
            n_ticks_override=n_ticks_override,
            persona_set=persona_set,
            seed=seed,
            temperature=temperature,
            on_event=observed_event,
            cancel=cancel,
            pause=pause,
            checkpoint_out=checkpoint_out,
            data_dir=data_dir,
            api_key=api_key,
            base_url=base_url,
            model=model,
            agent_loop_observer=_observed_agent_loop_observer(
                agent_loop_observer, telemetry,
            ),
        )
    except BaseException as exc:
        telemetry.record_fatal_error(exc)
        raise
    finally:
        telemetry.close()


def resume_stream(
    *,
    resume_checkpoint: str,
    on_event: EventCallback,
    cancel: Optional[threading.Event] = None,
    pause: Optional[threading.Event] = None,
    checkpoint_out: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    agent_loop_observer: AgentLoopObserver | None = None,
) -> None:
    """Resume a simulation with optional, fail-open observability."""
    session_id = f"poly:{uuid.uuid4()}"
    telemetry = create_observability(
        get_settings(),
        session_id=session_id,
        metadata={"mode": "resume"},
    )

    def observed_event(kind: str, payload: dict) -> None:
        telemetry.on_runner_event(kind, payload)
        on_event(kind, payload)

    try:
        _resume_stream_impl(
            resume_checkpoint=resume_checkpoint,
            on_event=observed_event,
            cancel=cancel,
            pause=pause,
            checkpoint_out=checkpoint_out,
            api_key=api_key,
            base_url=base_url,
            model=model,
            agent_loop_observer=_observed_agent_loop_observer(
                agent_loop_observer, telemetry,
            ),
        )
    except BaseException as exc:
        telemetry.record_fatal_error(exc)
        raise
    finally:
        telemetry.close()


def _run_tick_loop(
    *,
    env: PolyEnv,
    obs: dict,
    meta: dict,
    priors: dict,
    n_ticks: int,
    start_tick: int,
    slug: str,
    persona_set: str,
    seed: int,
    temperature: float,
    prev_yes_mid: Optional[float],
    api_key: str,
    base_url: Optional[str],
    model: Optional[str],
    settings,
    on_event: EventCallback,
    cancel: Optional[threading.Event],
    pause: Optional[threading.Event],
    checkpoint_out: Optional[str],
    started_at: dt.datetime,
    agent_loop_observer: AgentLoopObserver | None = None,
    agent_scheduler: AgentScheduler | None = None,
    interaction_budget: InteractionBudget = DEFAULT_INTERACTION_BUDGET,
) -> None:
    """Shared tick loop for fresh runs and resumes.

    Runs ticks `[start_tick, n_ticks)`. At each tick boundary it checks
    `pause`: if set (and a `checkpoint_out` path is configured), it writes
    a checkpoint capturing the env state *before* the upcoming tick, emits
    `paused`, and returns without settling. `cancel` short-circuits as
    before (emits `cancelled`, no checkpoint).
    """
    sim = env.state
    scheduler = agent_scheduler or SequentialAgentScheduler()
    transcript = getattr(sim, "interaction_transcript", None)
    if transcript is None:
        # Backwards compatibility for checkpoints created before VER-17.
        transcript = InteractionTranscript()
        sim.interaction_transcript = transcript
    interaction_adapter = ForumInteractionAdapter(
        run_id=str(sim.sim_id),
        agent_ids=(agent.agent_id for agent in sim.agents),
        transcript=transcript,
    )
    evaluation = AgentEvaluationSession(
        run_id=str(sim.sim_id),
        interaction_budget=interaction_budget,
        model=str(model or ""),
        schedules=list(getattr(sim, "evaluation_schedules", ())),
        beliefs=list(getattr(sim, "evaluation_beliefs", ())),
        prompt_versions=set(getattr(sim, "evaluation_prompt_versions", ())),
    )
    evaluation_observer = AgentLoopEvaluationObserver()
    observed_loop: AgentLoopObserver = evaluation_observer
    if agent_loop_observer is not None:
        observed_loop = CompositeAgentLoopObserver((
            agent_loop_observer,
            evaluation_observer,
        ))

    for tick in range(start_tick, n_ticks):
        if cancel is not None and cancel.is_set():
            on_event("cancelled", {"tick": tick})
            return
        # Pause at the tick boundary: snapshot everything needed to resume
        # exactly here (the env has not yet run `tick`).
        if pause is not None and pause.is_set() and checkpoint_out:
            save_checkpoint(
                checkpoint_out,
                sim=sim, rng=env._rng, next_tick=tick, n_ticks=n_ticks,
                slug=slug, persona_set=persona_set, seed=seed,
                temperature=temperature, market_meta=meta, priors=priors,
                prev_yes_mid=prev_yes_mid,
            )
            on_event("paused", {"tick": tick, "checkpoint": checkpoint_out})
            return

        tick_started = time.time()
        on_event("tick_started", {
            "tick": tick, "total": n_ticks,
            "yes_mid": float(sim.yes_mid),
        })

        # Decision scheduling is explicit and replaceable. The default keeps
        # the prior sequential observer order. Market execution still uses the
        # environment's seeded shuffle, preserving matching semantics.
        try:
            schedule = validate_schedule(
                scheduler.schedule(
                    tick=tick,
                    agent_ids=tuple(int(agent_id) for agent_id in obs),
                ),
                obs,
                expected_tick=tick,
            )
        except Exception as exc:  # noqa: BLE001 - invalid scheduler is fatal
            on_event("error", {
                "where": "agent_scheduler",
                "tick": tick,
                "scheduler": getattr(
                    scheduler, "name", type(scheduler).__name__,
                ),
                "message": str(exc),
            })
            return
        on_event("agent_schedule", {
            "tick": tick,
            "scheduler": schedule.scheduler,
            "decision_order": list(schedule.decision_order),
            "execution_order": "environment_seeded_shuffle",
        })
        evaluation.record_schedule(
            tick=tick,
            decision_order=schedule.decision_order,
        )
        _sync_evaluation_state(sim, evaluation)

        actions: dict = {}
        for aid in schedule.decision_order:
            if cancel is not None and cancel.is_set():
                on_event("cancelled", {"tick": tick, "agent_id": aid})
                return
            market_snap, agent_snap = obs[aid]
            agent = next(a for a in sim.agents if a.agent_id == aid)
            t0 = time.time()
            loop_context = AgentLoopContext.create(
                run_id=str(sim.sim_id),
                tick=tick,
                agent_id=int(aid),
            )

            # A budget-exhausted agent must not call the provider again.
            # Emit a deterministic HOLD for the remaining ticks instead.
            if agent.budget_exceeded:
                total_tokens = (
                    agent.total_prompt_tokens + agent.total_completion_tokens
                )
                decision = _budget_hold_decision(
                    total_tokens=total_tokens,
                    token_budget=agent.token_budget,
                    decision_id=loop_context.decision_id,
                )
                agent.n_holds += 1
                on_event("agent_budget_hold", {
                    "tick": tick,
                    "agent_id": aid,
                    "total_tokens": total_tokens,
                    "budget": agent.token_budget,
                })
                actions[aid] = decision
                _emit_decision_scores(
                    evaluation=evaluation,
                    decision=decision,
                    tick=tick,
                    agent_id=aid,
                    tick_size=float(priors["tick_size"]),
                    token_budget=int(agent.token_budget),
                    total_tokens=total_tokens,
                    lifecycle_events=[],
                    on_event=on_event,
                )
                _sync_evaluation_state(sim, evaluation)
                on_event("agent_decision", {
                    "tick": tick, "agent_id": aid,
                    "persona_type": agent.persona.persona_type,
                    "order_type": decision.order_type,
                    "outcome": decision.outcome,
                    "side": decision.side,
                    "price": float(decision.price),
                    "size_usd": float(decision.size_usd),
                    "reasoning": decision.reasoning,
                    "api_latency_ms": 0,
                    "api_error": decision.api_error,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "elapsed_s": 0.0,
                    "decision_id": decision.decision_id,
                    "prompt_metadata": _public_prompt_metadata(decision),
                })
                continue

            # Log every live web search this agent runs this tick. Web
            # search is NOT bit-for-bit reproducible (results change over
            # time); emitting the actual query + results preserves
            # auditability / replay of what the agent actually saw.
            def _on_info_query(query, results, _aid=aid, _tick=tick):
                on_event("agent_info_query", {
                    "tick": _tick, "agent_id": _aid,
                    "query": query,
                    "n_items_returned": len(results),
                    "results": [r.to_dict() for r in results],
                })

            # Emit a forum_* event the moment a social action is applied to
            # sim.forum, so the social-diffusion layer can be observed /
            # audited / replayed. The forum *mechanism* is deterministic;
            # the post/comment text is LLM-generated, so logging it here is
            # what preserves auditability of the social content.
            def _on_forum_action(kind, payload, _aid=aid, _tick=tick):
                messages = interaction_adapter.record(kind, payload)
                if kind == "post":
                    on_event("forum_post", payload)
                elif kind == "comment":
                    on_event("forum_comment", payload)
                elif kind == "follow":
                    on_event("forum_follow", payload)
                for message in messages:
                    on_event("multi_agent_interaction", message.to_record())

            try:
                with _LLM_SEMAPHORE:
                    decision = decide(
                        persona=agent.persona,
                        question=meta["question"],
                        description=meta.get("description", ""),
                        end_date=meta.get("end_date_iso", ""),
                        market=market_snap, agent=agent_snap,
                        api_key=api_key,
                        base_url=base_url,
                        model=model,
                        tick_size=priors["tick_size"],
                        temperature=temperature,
                        timeout=settings.DEEPSEEK_TIMEOUT,
                        max_attempts=3,
                        info_enabled=True,
                        on_info_query=_on_info_query,
                        forum=sim.forum,
                        agent_id=aid,
                        tick=tick,
                        forum_enabled=True,
                        on_forum_action=_on_forum_action,
                        loop_context=loop_context,
                        observer=observed_loop,
                        interaction_budget=interaction_budget,
                        loop_metadata={
                            "persona_type": agent.persona.persona_type,
                            "token_budget": int(agent.token_budget),
                            "persona_set": persona_set,
                            "market_slug": slug,
                        },
                    )
            except Exception as exc:        # noqa: BLE001
                evaluation_observer.pop(loop_context.decision_id)
                on_event("agent_decision_error", {
                    "tick": tick, "agent_id": aid, "message": str(exc),
                    "decision_id": loop_context.decision_id,
                })
                agent.n_errors += 1
                continue

            # Injectable/legacy decide implementations may omit the additive
            # identity field; runner context remains the canonical fallback.
            if not decision.decision_id:
                decision = replace(decision, decision_id=loop_context.decision_id)
            lifecycle_events = evaluation_observer.pop(loop_context.decision_id)

            # --- Track per-agent stats ---
            agent.n_decisions += 1
            agent.total_prompt_tokens += decision.prompt_tokens
            agent.total_completion_tokens += decision.completion_tokens
            agent.total_latency_ms += decision.api_latency_ms
            if decision.timeout_exceeded:
                agent.n_timeouts += 1
            if decision.api_error:
                agent.n_errors += 1
            if decision.order_type == "HOLD":
                agent.n_holds += 1

            # Budget check: once an agent exceeds its token budget, force
            # HOLD for the rest of the run and flag it. 0 = unlimited.
            if agent.token_budget > 0 and not agent.budget_exceeded:
                total_tokens = agent.total_prompt_tokens + agent.total_completion_tokens
                if total_tokens >= agent.token_budget:
                    agent.budget_exceeded = True
                    if decision.order_type != "HOLD":
                        agent.n_holds += 1
                    decision = _budget_hold_decision(
                        total_tokens=total_tokens,
                        token_budget=agent.token_budget,
                        decision=decision,
                        decision_id=loop_context.decision_id,
                    )
                    on_event("agent_budget_exceeded", {
                        "tick": tick, "agent_id": aid,
                        "total_tokens": total_tokens,
                        "budget": agent.token_budget,
                    })

            actions[aid] = decision
            _emit_decision_scores(
                evaluation=evaluation,
                decision=decision,
                tick=tick,
                agent_id=aid,
                tick_size=float(priors["tick_size"]),
                token_budget=int(agent.token_budget),
                total_tokens=(
                    agent.total_prompt_tokens + agent.total_completion_tokens
                ),
                lifecycle_events=lifecycle_events,
                on_event=on_event,
            )
            _sync_evaluation_state(sim, evaluation)
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
                "prompt_tokens": int(decision.prompt_tokens),
                "completion_tokens": int(decision.completion_tokens),
                "elapsed_s": round(time.time() - t0, 2),
                "decision_id": decision.decision_id,
                "prompt_metadata": _public_prompt_metadata(decision),
            })

        obs, info = env.step(actions)
        on_event("tick_finished", {
            "tick": tick, "n_fills": int(info["n_fills"]),
            "elapsed_s": round(time.time() - tick_started, 2),
            **_market_snapshot_dict(sim),
        })

        # Eval layer: macro tick metrics + micro per-agent snapshots, streamed
        # for the live observation page (see sim/evaluation/schema.py).
        tm = compute_tick_metrics(
            tick, sim.yes_mid, sim.no_mid, int(info["n_fills"]), prev_yes_mid,
        )
        on_event("tick_metrics", asdict(tm))
        on_event("agent_snapshots", {
            "tick": tick,
            "agents": [asdict(s) for s in
                       snapshot_all(tick, sim.agents, sim.yes_mid, sim.no_mid)],
        })
        prev_yes_mid = float(sim.yes_mid)

    # 6. Settle (no-op for unresolved markets) + final summary.
    pnl = env.settle()
    agent_stats = {
        a.agent_id: {
            "persona_type": a.persona.persona_type,
            "n_decisions": a.n_decisions,
            "n_errors": a.n_errors,
            "n_holds": a.n_holds,
            "n_timeouts": a.n_timeouts,
            "total_prompt_tokens": a.total_prompt_tokens,
            "total_completion_tokens": a.total_completion_tokens,
            "total_tokens": a.total_prompt_tokens + a.total_completion_tokens,
            "total_latency_ms": a.total_latency_ms,
            "avg_latency_ms": (
                round(a.total_latency_ms / a.n_decisions, 1)
                if a.n_decisions else 0
            ),
            "budget_exceeded": a.budget_exceeded,
        }
        for a in sim.agents
    }
    try:
        run_scores = evaluation.score_run(
            messages=transcript.messages,
            expected_agent_ids=[agent.agent_id for agent in sim.agents],
            final_yes=float(sim.yes_mid),
            resolved_yes=sim.market_resolved_yes,
        )
        on_event("run_scores", {
            "run_id": str(sim.sim_id),
            "scores": [score.to_record() for score in run_scores],
        })
    except Exception as exc:  # noqa: BLE001 - eval is fail-open
        log.warning("Run evaluation failed", exc_info=True)
        on_event("evaluation_error", {
            "scope": "run",
            "run_id": str(sim.sim_id),
            "message": str(exc),
        })
    on_event("settled", {
        "pnl": {int(k): float(v) for k, v in pnl.items()},
        "n_actions": len(sim.actions_log),
        "n_fills": len(sim.fills_log),
        "yes_mid_final": float(sim.yes_mid),
        "wall_seconds": round(
            (dt.datetime.utcnow() - started_at).total_seconds(), 1,
        ),
        "agent_stats": agent_stats,
        "n_interactions": len(transcript.messages),
    })
    on_event("done", {"sim_id": sim.sim_id})
