#!/usr/bin/env python3
"""Step 7 of 8 — Render the 6 paper figures.

Produces matplotlib + seaborn PNG/PDF figures in `figures/`:
  - fig1_market_landscape.{png,pdf}      market volume + lifetime distribution
  - fig2_wallet_population.{png,pdf}     calibrated population: capital, accuracy
  - fig3_price_path.{png,pdf}            sim YES mid vs real CLOB path
  - fig4_serd_roi.{png,pdf}              ROI by SERD quartile (predator → prey)
  - fig5_serd_vs_baseline.{png,pdf}      SERD ΔROI vs DBSCAN+KMeans
  - fig6_action_mix.{png,pdf}            BUY/SELL/CANCEL/HOLD frequency by tick

Reads from ClickHouse — both real (`dataapi_trades`,
`clob_prices_history`) and sim (`agent_*`) tables. Gracefully handles
empty sim tables (placeholder "no v7 sim runs yet" panels).

Usage:
    python scripts/07_render_figures.py --output-dir figures/
    python scripts/07_render_figures.py --slug <slug> --sim-id <hex>
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 7 of 8 — Render figures\n")
    from src.analysis.plots import main
    main()
