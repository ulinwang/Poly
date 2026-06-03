"""Generate v15 thesis experiment configs.

v15 is the final thesis rerun suite after the two-stage agent redesign:
each regular decision tick first updates belief, then optionally takes one
trade action. All thesis-facing runs use one seed and write to output/v15.

Run:
    uv run python scripts/gen_v15_experiment_configs.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "experiments" / "configs" / "v15"

SEED = 0
BASELINE_TICKS = 20
BASELINE_AGENTS = 20

BASE = {
    "robotaxi": "will-tesla-launch-a-driverless-robotaxi-service-by-october-31",
    "ethereum": "will-ethereum-reach-5000-in-august-614-348-169-974-494",
}

PANEL = {
    "m01": "tesla-launches-unsupervised-full-self-driving-fsd-by-october-31-717-337",
    "m02": "will-trump-deploy-national-guard-in-dc-by-monday",
    "m03": "will-the-supreme-court-rule-in-favor-of-trumps-tariffs",
    "m04": "katy-perry-and-justin-trudeau-confirmed-relationship-by-october-31",
    "m05": "will-bitcoin-reach-125k-in-july-846-114",
    "m06": "btc-above-100k-till-2025-end",
    "m07": "will-microstrategy-purchase-bitcoin-august-26-september-1",
    "m08": "nfl-kc-nyg-2025-09-21",
    "m09": "nfl-bal-buf-2025-09-07",
    "m10": "lord-miles-completes-40-day-water-fast-in-the-dessert",
}

ACTIVE_VALIDATION = (
    "will-the-chopsticks-catch-spacex-starship-flight-test-11-superheavy-booster"
)

MIX = {
    "natural": None,
    "uniform": [1, 1, 1, 1, 1, 1],
    "concentrated": [0.5, 0.1, 0.1, 0.1, 0.1, 0.1],
}


def cfg(
    name: str,
    slug: str,
    *,
    output_dir: str,
    desc: str,
    n_agents: int = BASELINE_AGENTS,
    n_ticks: int = BASELINE_TICKS,
    belief: bool = True,
    thinking: bool | None = False,
    archetype_weights: list[float] | None = None,
    prompt_language: str = "en",
    checkpoint: bool = False,
) -> str:
    lines = [
        f"name: {name}",
        "description: |",
        *[f"  {ln}" for ln in desc.strip().splitlines()],
        "market:",
        f"  slug: {slug}",
        "  asof: market_open",
        "agent:",
        "  population: archetype",
        f"  n_agents: {n_agents}",
        f"  seed: {SEED}",
        f"  belief_update_enabled: {str(belief).lower()}",
    ]
    if archetype_weights is not None:
        lines.append(f"  archetype_weights: {archetype_weights}")
    lines += [
        "environment:",
        "  observer: quote_only",
        "  seeder: from_clob_history",
        "  fees_override_bps: 0",
        "llm:",
        "  model: null",
        "  temperature: 1.0",
        "  timeout_s: 120.0",
        "  retry: {max_attempts: 3, backoff_base_s: 2.0}",
        f"  concurrency: {n_agents}",
    ]
    if thinking is not None:
        lines.append(f"  thinking: {str(thinking).lower()}")
    if prompt_language != "en":
        lines.append(f"  prompt_language: {prompt_language}")
    lines += [
        "experiment:",
        f"  n_ticks_override: {n_ticks}",
    ]
    if checkpoint:
        lines += [
            "  checkpoint_enabled: true",
            "  checkpoint_interval_ticks: 5",
            "  checkpoint_compact_char_budget: 60000",
            "  checkpoint_recent_ticks: 5",
        ]
    lines += [
        "output:",
        "  dual_write_clickhouse: false",
        "  parquet_compression: zstd",
        f"  output_dir: {output_dir}",
    ]
    return "\n".join(lines) + "\n"


def write(name: str, text: str) -> None:
    (OUT / f"{name}.yaml").write_text(text)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.yaml"):
        old.unlink()

    n = 0

    # Smoke config is not part of the 41 thesis runs.
    write(
        "smoke_2agent_t3",
        cfg(
            "smoke_2agent_t3",
            BASE["robotaxi"],
            n_agents=2,
            n_ticks=3,
            output_dir="output/v15/smoke",
            desc="Smoke test for v15 two-stage belief then trade loop.",
            checkpoint=True,
        ),
    )

    for market_key, slug in BASE.items():
        for n_agents in (10, 20, 50, 100):
            name = f"c1_{market_key}_n{n_agents}_s{SEED}"
            write(
                name,
                cfg(
                    name,
                    slug,
                    n_agents=n_agents,
                    output_dir=f"output/v15/c1_{market_key}",
                    desc=(
                        f"v15 scale experiment ({market_key}), "
                        f"{n_agents} agents, seed {SEED}."
                    ),
                ),
            )
            n += 1

        for n_ticks in (10, 20, 50, 100):
            name = f"c3_{market_key}_t{n_ticks}_s{SEED}"
            write(
                name,
                cfg(
                    name,
                    slug,
                    n_ticks=n_ticks,
                    output_dir=f"output/v15/c3_{market_key}",
                    desc=(
                        f"v15 tick-horizon experiment ({market_key}), "
                        f"{n_ticks} rounds, seed {SEED}."
                    ),
                ),
            )
            n += 1

        for variant, weights in MIX.items():
            name = f"c4_{market_key}_{variant}_s{SEED}"
            write(
                name,
                cfg(
                    name,
                    slug,
                    archetype_weights=weights,
                    output_dir=f"output/v15/c4_{market_key}",
                    desc=(
                        f"v15 profile-distribution experiment "
                        f"({market_key}), {variant} mix, seed {SEED}."
                    ),
                ),
            )
            n += 1

        # DeepSeek's thinking mode does not currently support forced
        # tool_choice, which v15 needs for the mandatory belief stage.
        # Keep this as a prompt-level reasoning-control placeholder by
        # running both settings with API thinking disabled; downstream
        # analysis should treat c5 as non-primary until a compatible
        # model/tool protocol is available.
        for mode, thinking in (("on", False), ("off", False)):
            name = f"c5_{market_key}_{mode}_s{SEED}"
            write(
                name,
                cfg(
                    name,
                    slug,
                    thinking=thinking,
                    output_dir=f"output/v15/c5_{market_key}",
                    desc=(
                        f"v15 thinking-mode experiment ({market_key}), "
                        f"thinking {mode}, seed {SEED}."
                    ),
                ),
            )
            n += 1

        for mode, belief in (("on", True), ("off", False)):
            name = f"c6_{market_key}_belief_{mode}_s{SEED}"
            write(
                name,
                cfg(
                    name,
                    slug,
                    belief=belief,
                    output_dir=f"output/v15/c6_{market_key}",
                    desc=(
                        f"v15 belief-stage ablation ({market_key}), "
                        f"belief {mode}, seed {SEED}."
                    ),
                ),
            )
            n += 1

    for market_id, slug in PANEL.items():
        name = f"rq1_{market_id}_s{SEED}"
        write(
            name,
            cfg(
                name,
                slug,
                output_dir="output/v15/rq1_panel",
                desc=f"v15 cross-market panel, market {market_id}, seed {SEED}.",
            ),
        )
        n += 1

    name = f"rq5_spacex_s{SEED}"
    write(
        name,
        cfg(
            name,
            ACTIVE_VALIDATION,
            output_dir="output/v15/rq5_spacex",
            desc=(
                "v15 active-market validation after close "
                "(SpaceX Flight Test 11 booster catch), seed 0."
            ),
        ),
    )
    n += 1

    print(f"wrote {n} thesis configs plus 1 smoke config to {OUT}")


if __name__ == "__main__":
    main()
