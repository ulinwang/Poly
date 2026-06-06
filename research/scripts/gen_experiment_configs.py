"""Generate the v14 experiment-suite configs for the re-run.

Produces YAML configs under ``experiments/configs/v14/`` for:
  - c1 scale  (agent count 10/20/50/100)   x 2 base markets
  - c3 tick   (horizon 10/20/50/100)        x 2 base markets
  - c4 profile-mix (natural/uniform/concentrated) x 2 base markets
  - c5 thinking (on/off)                    x 2 base markets
  - rq1 cross-market panel (10 markets)
  - rq5 open-market preview (1 market)

Every config holds the shared baseline fixed (archetype population,
20 agents, 20 ticks, temperature 1.0, belief on, no shock) and only
varies the parameter under study.

Run:  uv run python scripts/gen_experiment_configs.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLUGS = json.loads((Path("/tmp/final_slugs.json")).read_text())
OUT = ROOT / "experiments" / "configs" / "v14"
OUT.mkdir(parents=True, exist_ok=True)

BASE = {"robotaxi": SLUGS["base_yes"], "ethereum": SLUGS["base_no"]}
PANEL = {f"m{i:02d}": SLUGS[f"p{i:02d}"] for i in range(1, 11)}

SEEDS = (0, 1, 2)
BASELINE_TICKS = 20
# c4 profile-mix weight vectors over the K=6 clusters.
MIX = {
    "natural": None,                                  # empirical proportions
    "uniform": [1, 1, 1, 1, 1, 1],                    # equal weight
    "concentrated": [0.5, 0.1, 0.1, 0.1, 0.1, 0.1],   # cluster 0 dominant
}


def cfg(name, slug, *, n_agents=20, seed=0, n_ticks=BASELINE_TICKS,
        population="archetype", belief=True, thinking=None,
        archetype_weights=None, output_dir, desc):
    """Render one experiment YAML string."""
    lines = [
        f"name: {name}",
        "description: |",
        *[f"  {ln}" for ln in desc.strip().splitlines()],
        "market:",
        f"  slug: {slug}",
        "  asof: market_open",
        "agent:",
        f"  population: {population}",
        f"  n_agents: {n_agents}",
        f"  seed: {seed}",
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
        "  concurrency: null",
    ]
    if thinking is not None:
        lines.append(f"  thinking: {str(thinking).lower()}")
    lines += [
        "experiment:",
        f"  n_ticks_override: {n_ticks}",
        "output:",
        "  dual_write_clickhouse: false",
        "  parquet_compression: zstd",
        f"  output_dir: {output_dir}",
    ]
    return "\n".join(lines) + "\n"


def write(name, text):
    (OUT / f"{name}.yaml").write_text(text)


def main():
    n = 0
    for tag, slug in BASE.items():
        # --- c1 scale ---
        for na in (10, 20, 50, 100):
            for s in SEEDS:
                nm = f"c1_{tag}_n{na}_s{s}"
                write(nm, cfg(nm, slug, n_agents=na, seed=s,
                              output_dir=f"output/v14/c1_{tag}",
                              desc=f"Scale experiment ({tag} base market), "
                                   f"{na} agents, seed {s}."))
                n += 1
        # --- c3 tick ---
        for t in (10, 20, 50, 100):
            for s in SEEDS:
                nm = f"c3_{tag}_t{t}_s{s}"
                write(nm, cfg(nm, slug, seed=s, n_ticks=t,
                              output_dir=f"output/v14/c3_{tag}",
                              desc=f"Tick-horizon experiment ({tag} base "
                                   f"market), {t} rounds, seed {s}."))
                n += 1
        # --- c4 profile-mix ---
        for variant, w in MIX.items():
            for s in SEEDS:
                nm = f"c4_{tag}_{variant}_s{s}"
                write(nm, cfg(nm, slug, seed=s, archetype_weights=w,
                              output_dir=f"output/v14/c4_{tag}",
                              desc=f"Profile-distribution experiment "
                                   f"({tag} base), {variant} mix, seed {s}."))
                n += 1
        # --- c5 thinking ---
        for mode, th in (("on", True), ("off", False)):
            for s in SEEDS:
                nm = f"c5_{tag}_{mode}_s{s}"
                write(nm, cfg(nm, slug, seed=s, thinking=th,
                              output_dir=f"output/v14/c5_{tag}",
                              desc=f"Thinking-mode experiment ({tag} base), "
                                   f"thinking {mode}, seed {s}."))
                n += 1
    # --- rq1 cross-market panel ---
    for mk, slug in PANEL.items():
        for s in SEEDS:
            nm = f"rq1_{mk}_s{s}"
            write(nm, cfg(nm, slug, seed=s,
                          output_dir="output/v14/rq1_panel",
                          desc=f"Cross-market panel, market {mk}, seed {s}."))
            n += 1
    # --- rq5 open-market preview ---
    for s in SEEDS:
        nm = f"rq5_s{s}"
        write(nm, cfg(nm, SLUGS["rq5"], seed=s,
                      output_dir="output/v14/rq5_open",
                      desc=f"Open-market preview (Thunder NBA Finals), "
                           f"seed {s}."))
        n += 1
    print(f"wrote {n} configs to {OUT}")


if __name__ == "__main__":
    main()
