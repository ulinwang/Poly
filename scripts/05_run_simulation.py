#!/usr/bin/env python3
"""Step 5 of 8 — Run the multi-agent CLOB simulation.

Loads `data/priors_<slug>.json` and the cached personas, instantiates
the calibrated agent population, and steps the CLOB engine for the
priors-derived `n_ticks`. Every action / fill / position is persisted
to ClickHouse (sim_id, agent_simulations, agent_actions, agent_fills,
agent_positions, agent_personas).

Wall-clock: dominated by LLM latency. ~50 wallets × ~30 ticks ×
~3s/call ≈ 75 minutes per sim. Use `--dry-run` first to preview.

Usage:
    python scripts/05_run_simulation.py --slug <chosen-slug>
    python scripts/05_run_simulation.py --slug <slug> --seed-liquidity \\
        --notes "v7 reference run"
    python scripts/05_run_simulation.py --slug <slug> --dry-run
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 5 of 8 — Run multi-agent simulation\n")
    import sys
    # v7: --population calibrated is the only supported path — auto-inject
    # so the user doesn't have to remember.
    if "--population" not in sys.argv:
        sys.argv.extend(["--population", "calibrated"])
    from src.pipeline.runner import main
    main()
