#!/usr/bin/env python3
"""Step 0 of 8 — Ingest Polymarket Gamma /markets into ClickHouse.

Calls `src/ingest/gamma_full.py`. Full-fidelity ~125-field market
metadata; populates the `markets_full` table from which the
`markets_resolved` view is computed.

Tables populated:
  - markets_full       (~146k unique markets, full Gamma payload)
  - markets_resolved   (view: closed markets with resolution outcome)

Usage: see `python -m src.ingest.gamma_full --help`. Pass-through.
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 0 of 8 — Ingest Gamma into ClickHouse")
    from src.ingest.gamma_full import main
    main()
