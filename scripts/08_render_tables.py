#!/usr/bin/env python3
"""Step 8 of 8 — Render the paper tables in markdown + LaTeX.

Outputs to `tables/`:
  - tab1_wallet_population.{md,tex}   per-decile population summary
  - tab2_serd_roles.{md,tex}          ROI + n_agents per quartile role
  - tab3_vs_baseline.{md,tex}         SERD vs DBSCAN+KMeans ΔROI
  - tab4_priors_summary.{md,tex}      every prior + its data source

Reads from ClickHouse (sim tables) plus `data/priors_<slug>.json`.

Usage:
    python scripts/08_render_tables.py --slug <slug> --sim-id <hex>
    python scripts/08_render_tables.py --slug <slug> --output-dir tables/
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 8 of 8 — Render tables\n")
    from src.thesis.tables import main
    main()
