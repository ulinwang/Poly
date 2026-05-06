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

from ..clickhouse_client import ClickHouse
from ..config import get_settings
from . import clob_history, comparison
from .env import make_sim, run_simulation, settle
from .personas import DEFAULT_PERSONAS, Persona, assign_personas


log = logging.getLogger(__name__)


def _load_market(ch: ClickHouse, slug: str) -> dict:
    row = ch.fetch_market_by_slug(slug)
    if not row:
        raise SystemExit(f"no market with slug={slug!r} in markets table")
    market_id, slug_, question, description, outcomes, clob_token_ids, \
        outcome_prices, volume, end_date, closed = row
    resolved = None
    if closed and outcome_prices:
        try:
            yes = float(outcome_prices[0])
            no = float(outcome_prices[1]) if len(outcome_prices) > 1 else 1.0 - yes
            if yes >= 0.99 and no <= 0.01:
                resolved = 1
            elif no >= 0.99 and yes <= 0.01:
                resolved = 0
        except (ValueError, TypeError, IndexError):
            pass
    return {
        "market_id": market_id, "slug": slug_,
        "question": question, "description": description or "",
        "outcomes": list(outcomes),
        "clob_token_ids": list(clob_token_ids),
        "volume": float(volume or 0.0),
        "end_date": end_date,
        "closed": bool(closed),
        "resolved_yes": resolved,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True,
                        help="Polymarket market slug to simulate")
    parser.add_argument("--n-ticks", type=int, default=24)
    parser.add_argument("--n-agents", type=int, default=10)
    parser.add_argument("--taker-fee-bps", type=float, default=0.0,
                        help="taker fee in basis points (100 = 1%)")
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
    parser.add_argument(
        "--n-wallets", type=int, default=20,
        help="number of wallets to sample when --population=calibrated",
    )
    parser.add_argument(
        "--capital-scale", type=float, default=1.0,
        help="multiplier on wallet capital (e.g. 0.1 to keep notionals small)",
    )
    parser.add_argument(
        "--cutoff-days-before-end", type=int, default=60,
        help="for calibration, days before market end_date to use as data cutoff",
    )
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

    # ----- Population assembly: legacy personas vs v4 wallet calibration -----
    if args.population == "calibrated":
        from . import wallet_calibration, persona_generator, initialization
        ch.ensure_wallet_features_schema()
        # Phase 1: calibrate wallets if not already populated for this market
        existing = ch.fetch_wallet_features(market["market_id"])
        if not existing:
            log.info("no wallet_features yet — running calibration "
                     "(this hits Polymarket data-api; can take a few minutes)")
            wallet_calibration.calibrate(
                slug=market["slug"], n_wallets=args.n_wallets,
                cutoff_days_before_end=args.cutoff_days_before_end,
            )
        else:
            log.info("reusing %s cached wallet_features rows", len(existing))
        # Phase 2: persona profiles
        persona_generator.generate_for_market(
            target_market_id=str(market["market_id"]), force=False, ch=ch,
        )
        # Phase 3: build population
        yes_token_id = market["clob_token_ids"][0] if market["clob_token_ids"] else ""
        population = initialization.build_population(
            target_market_id=str(market["market_id"]),
            yes_token_id=yes_token_id,
            capital_scale=args.capital_scale, ch=ch,
        )
        if not population:
            raise SystemExit("calibrated population is empty; "
                             "check wallet_features and wallet_personas.json cache")
        log.info("calibrated population: %s agents", len(population))
        sim = make_sim(
            market_id=market["market_id"], market_slug=market["slug"],
            question=market["question"], description=market["description"],
            end_date_str=end_date_str,
            market_resolved_yes=market["resolved_yes"],
            population=population, n_ticks=args.n_ticks,
            taker_fee_bps=args.taker_fee_bps,
        )
    else:
        personas = assign_personas(args.n_agents, DEFAULT_PERSONAS)
        sim = make_sim(
            market_id=market["market_id"], market_slug=market["slug"],
            question=market["question"], description=market["description"],
            end_date_str=end_date_str,
            market_resolved_yes=market["resolved_yes"],
            personas=personas, n_ticks=args.n_ticks,
            taker_fee_bps=args.taker_fee_bps,
        )

    # Optional bootstrap liquidity (v4): seed both books with passive maker
    if args.seed_liquidity:
        from .env import seed_orderbook_liquidity
        seed_orderbook_liquidity(sim)
        log.info("seeded environmental orderbook liquidity (agent_id=-1)")

    log.info("sim_id=%s n_agents=%d n_ticks=%d taker_fee_bps=%.1f",
             sim.sim_id, len(sim.agents), sim.n_ticks, sim.taker_fee_bps)

    if args.dry_run:
        from .agent import AgentSnapshot, MarketSnapshot, build_user_prompt, _build_clob_system_prompt
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

    if not args.skip_clob and market["clob_token_ids"]:
        for token_id in market["clob_token_ids"]:
            log.info("fetching real CLOB trades for token %s...", token_id[:16] + "...")
            try:
                clob_history.fetch_and_store_trades(
                    ch, market_id=market["market_id"], token_id=token_id,
                )
            except Exception as exc:  # noqa: BLE001 — surface but don't crash
                log.warning("CLOB fetch failed for %s: %s", token_id[:16], exc)


if __name__ == "__main__":
    main()
