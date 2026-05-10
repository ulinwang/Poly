"""
Multi-agent Polymarket simulation runner.

Usage:
    uv run python -m src.sim --slug <market-slug>
    uv run python -m src.sim --slug ... --dry-run    # build prompts only
    uv run python -m src.sim --slug ... --skip-clob  # skip real-trades fetch
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from typing import Optional

from data.store.clickhouse import ClickHouse
from data.store.config import get_settings
from ..analysis import comparison
from ..core.env import make_sim, run_simulation, settle
from agent.personas.persona import Persona


log = logging.getLogger(__name__)


def _load_market(ch: ClickHouse, slug: str) -> dict:
    """v7: market identity is the on-chain `condition_id` (hex), not
    the legacy gamma integer id. Reads from clob_markets +
    markets_resolved + markets_full."""
    rows = ch.client.execute(
        f"""
        SELECT cm.condition_id, cm.market_slug, cm.question,
               cm.tokens_json, mf.description, mf.volume_num,
               mr.end_date, mr.outcomes, mr.winning_idx
        FROM polymetl.clob_markets cm
        LEFT JOIN polymetl.markets_resolved mr USING (condition_id)
        LEFT JOIN polymetl.markets_full mf USING (condition_id)
        WHERE cm.market_slug = %(slug)s
        LIMIT 1
        """,
        {"slug": slug},
    )
    if not rows:
        raise SystemExit(f"no market with slug={slug!r} in clob_markets")
    cid, slug_, question, tokens_json, description, volume, \
        end_date, outcomes, winning_idx = rows[0]
    tokens = json.loads(tokens_json or "[]")
    yes = next((t for t in tokens if str(t.get("outcome", "")).lower() == "yes"),
               tokens[0] if tokens else {})
    no = next((t for t in tokens if str(t.get("outcome", "")).lower() == "no"),
              tokens[-1] if tokens else {})
    clob_token_ids = [str(yes.get("token_id", "")), str(no.get("token_id", ""))]
    resolved = int(winning_idx) if winning_idx is not None and winning_idx >= 0 else None
    return {
        "market_id": cid,    # v7: condition_id is the canonical id
        "slug": slug_,
        "question": question or "",
        "description": description or "",
        "outcomes": list(outcomes) if outcomes else ["Yes", "No"],
        "clob_token_ids": clob_token_ids,
        "volume": float(volume or 0.0),
        "end_date": end_date,
        "closed": True,    # only resolved markets reach this code path in v7
        "resolved_yes": resolved,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True,
                        help="Polymarket market slug to simulate")
    parser.add_argument("--n-ticks", type=int, default=0,
                        help="0 = use the priors-derived n_ticks (recommended)")
    parser.add_argument("--n-agents", type=int, default=10,
                        help="ignored when --population calibrated (full pop used)")
    parser.add_argument("--taker-fee-bps", type=float, default=-1.0,
                        help="-1 = use clob_markets.taker_base_fee from priors "
                             "(recommended); else override in basis points")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-clob", action="store_true",
                        help="don't fetch real trade history")
    parser.add_argument("--reset-schema", action="store_true",
                        help="drop and recreate sim tables (destroys prior sim data)")
    parser.add_argument("--notes", default="",
                        help="free-text annotation stored in agent_simulations.notes")
    # v4 calibration flags
    parser.add_argument(
        "--population", choices=["personas", "calibrated"], default="personas",
        help="'personas' (legacy v2/v3 hand-coded archetypes) or "
             "'calibrated' (Phase 1-3: real wallet features → AgentInit)",
    )
    parser.add_argument(
        "--seed-liquidity", action="store_true",
        help="inject exogenous bootstrap orderbook before tick 0 "
             "(recommended for calibrated populations to avoid empty books)",
    )
    # v7: --n-wallets, --capital-scale, --fallback-cutoff-days-before-end
    # and the --seed-spread / --seed-depth-* knobs were removed. Every
    # value they previously controlled is now derived from
    # data/priors_<slug>.json; see docs/EMPIRICAL_PRIORS.md.
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = get_settings()
    if not settings.DEEPSEEK_API_KEY and not args.dry_run:
        raise SystemExit(
            "POLYMETL_DEEPSEEK_API_KEY is required (set it in .env). "
            "Use --dry-run for a structural preview."
        )

    ch = ClickHouse(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DATABASE,
    )
    if args.reset_schema:
        log.warning("--reset-schema: dropping all sim tables")
        ch.reset_sim_schema()
    ch.ensure_sim_schema()

    market = _load_market(ch, args.slug)
    log.info("loaded market: id=%s volume=$%.0f resolved_yes=%s",
             market["market_id"], market["volume"], market["resolved_yes"])

    end_date_str = market["end_date"].isoformat() if market["end_date"] else "unknown"

    # ----- v7: priors-driven calibrated population only -----
    consensus_mu: Optional[float] = None
    if args.population != "calibrated":
        raise SystemExit(
            "v7 requires --population calibrated. The hardcoded "
            "SkepticalEngineer/LotteryPlayer/etc. archetypes were "
            "removed in the v7 restructure (see docs/PAPER.md §3.2). "
            "Run: scripts/02_build_wallet_features.py + "
            "scripts/03_derive_calibration_priors.py + "
            "scripts/04_generate_personas.py first."
        )

    from agent.features import wallet as wallet_features
    from agent.personas import calibrated as persona_generator
    from agent.factory import init_agents
    ch.ensure_wallet_features_schema()
    # Phase 1: ensure wallet_features rows exist (SQL-only, no network).
    existing = ch.fetch_wallet_features(market["market_id"])
    if not existing:
        log.info("no wallet_features yet — running SQL calibration")
        wallet_features.calibrate(slug=market["slug"])
    else:
        log.info("reusing %d cached wallet_features rows", len(existing))
    # Phase 2: persona profiles (uses bio + display_name from dataapi_holders).
    persona_generator.generate_for_market(
        target_market_id=str(market["market_id"]), force=False, ch=ch,
    )

    # Phase 3: build population from priors JSON (everything data-derived).
    population, priors = init_agents(
        slug=market["slug"], ch=ch,
    )
    if not population:
        raise SystemExit("calibrated population is empty; "
                         "check wallet_features and wallet_personas.json cache")
    consensus_mu = float(priors["signal_mu"])
    n_ticks_eff = int(priors["n_ticks"]) if args.n_ticks <= 0 else args.n_ticks
    fee_bps_eff = float(priors["taker_fee_bps"]) if args.taker_fee_bps < 0 \
                  else args.taker_fee_bps
    log.info(
        "v7 priors loaded: signal_mu=%.3f n_ticks=%d taker_fee_bps=%.2f "
        "tick_size=%.4f bootstrap=%.3f/%.3f/%.0f (%s)",
        consensus_mu, n_ticks_eff, fee_bps_eff, priors["tick_size"],
        priors["bootstrap"]["anchor_yes"], priors["bootstrap"]["spread"],
        priors["bootstrap"]["depth_per_level"], priors["bootstrap"]["source"],
    )
    log.info("calibrated population: %d agents", len(population))
    sim = make_sim(
        market_id=market["market_id"], market_slug=market["slug"],
        question=market["question"], description=market["description"],
        end_date_str=end_date_str,
        market_resolved_yes=market["resolved_yes"],
        population=population, n_ticks=n_ticks_eff,
        taker_fee_bps=fee_bps_eff,
    )

    # Optional bootstrap liquidity (v4): seed both books with passive maker.
    # Anchor the YES book at consensus_mu (pre-event VWAP) and the NO book
    # at 1 - consensus_mu so the synthetic environmental MM does not impose
    # a 50/50 prior on a long-shot market.
    if args.seed_liquidity:
        from ..core.env import seed_orderbook_liquidity, ENV_MAKER_AGENT_ID
        # v7: ALL bootstrap params come from data-derived priors.
        boot = priors["bootstrap"]
        yes_anchor = max(0.05, min(0.95, float(boot["anchor_yes"])))
        seed_orderbook_liquidity(
            sim,
            yes_anchor=yes_anchor,
            no_anchor=1.0 - yes_anchor,
            spread=float(boot["spread"]),
            depth_levels=int(boot["depth_levels"]),
            depth_per_level=float(boot["depth_per_level"]),
        )
        log.info(
            "seeded environmental orderbook liquidity "
            "(agent_id=%d, yes_anchor=%.3f, spread=%.3f, %d×%.0f, source=%s)",
            ENV_MAKER_AGENT_ID, yes_anchor, boot["spread"],
            int(boot["depth_levels"]), float(boot["depth_per_level"]),
            boot["source"],
        )

    log.info("sim_id=%s n_agents=%d n_ticks=%d taker_fee_bps=%.1f",
             sim.sim_id, len(sim.agents), sim.n_ticks, sim.taker_fee_bps)

    if args.dry_run:
        from agent.decision import (
            AgentSnapshot, MarketSnapshot, build_user_prompt,
            _build_clob_system_prompt,
        )
        sample_market = MarketSnapshot(
            yes_best_bid=None, yes_best_ask=None, yes_mid=0.5,
            no_best_bid=None, no_best_ask=None, no_mid=0.5,
            yes_mid_history=[],
            ticks_remaining=sim.n_ticks, total_ticks=sim.n_ticks,
        )
        sample_agent = AgentSnapshot(0, sim.agents[0].cash, 0.0, 0.0, 0)
        log.info("[dry-run] system prompt sample (persona=%s):\n%s",
                 sim.agents[0].persona.persona_type,
                 _build_clob_system_prompt(
                     sim.agents[0].persona, sim.question,
                     sim.description, sim.end_date_str)[:700])
        log.info("[dry-run] user prompt sample:\n%s",
                 build_user_prompt(sample_market, sample_agent))
        log.info("[dry-run] would call %s for %d agents × %d ticks = %d LLM calls",
                 settings.DEEPSEEK_MODEL, len(sim.agents), sim.n_ticks,
                 len(sim.agents) * sim.n_ticks)
        return

    started_at = dt.datetime.utcnow()
    run_simulation(
        sim,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_MODEL,
    )
    ended_at = dt.datetime.utcnow()
    pnls = settle(sim)

    log.info("=" * 60)
    log.info("Simulation complete: %s", sim.sim_id)
    log.info("Final sim YES mid:  %.3f", sim.yes_mid)
    log.info("Final sim NO  mid:  %.3f", sim.no_mid)
    log.info("Market resolved YES: %s", sim.market_resolved_yes)
    if sim.market_resolved_yes is not None:
        ok = comparison.direction_correct(sim.yes_mid, sim.market_resolved_yes)
        log.info("Direction correct: %s", ok)
    by_persona: dict[str, list[float]] = {}
    for a in sim.agents:
        by_persona.setdefault(a.persona.persona_type, []).append(pnls.get(a.agent_id, 0.0))
    for ptype, vals in by_persona.items():
        avg = sum(vals) / len(vals)
        log.info("PnL %s: avg=$%.2f n=%d  vals=%s",
                 ptype, avg, len(vals),
                 [f"{v:+.0f}" for v in vals])

    # Persist to ClickHouse
    persona_rows = [
        (sim.sim_id, a.agent_id, a.persona.persona_type,
         a.persona.risk_aversion, a.persona.capital_initial,
         a.persona.profile_text)
        for a in sim.agents
    ]
    ch.insert_personas(persona_rows)
    ch.insert_actions(sim.actions_log)
    ch.insert_fills(sim.fills_log)
    ch.insert_positions(sim.positions_log)

    persona_set = ",".join(sorted({a.persona.persona_type for a in sim.agents}))
    notes_obj = {
        "engine": "CLOB",
        "taker_fee_bps": sim.taker_fee_bps,
        "user_notes": args.notes,
        "pnl_by_persona": {k: sum(v) / len(v) for k, v in by_persona.items()},
        "n_agents_per_persona": {k: len(v) for k, v in by_persona.items()},
    }
    ch.insert_simulation((
        sim.sim_id, sim.market_id, sim.market_slug,
        "CLOB", sim.taker_fee_bps,
        persona_set, len(sim.agents), sim.n_ticks,
        started_at, ended_at, sim.yes_mid,
        sim.market_resolved_yes, json.dumps(notes_obj),
    ))
    log.info("persisted simulation to ClickHouse: sim_id=%s", sim.sim_id)

    # v7: dropped the post-sim CLOB-history fetch. dataapi_trades
    # already covers 110k markets including this one, populated by
    # `python -m src.ingest.data_api`. The post-hoc real-vs-sim
    # comparison reads from there directly (see src/analysis/comparison.py).


if __name__ == "__main__":
    main()
