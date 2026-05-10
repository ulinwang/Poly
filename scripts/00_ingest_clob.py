#!/usr/bin/env python3
"""Step 0 of 8 — Ingest Polymarket CLOB endpoints into ClickHouse.

Calls the user-authored ETL at `src/ingest/clob_api.py`. Long-running:
walks the full /markets / /book / /prices-history / /trades surface
with resume markers in `clob_progress`. Safe to interrupt and resume.

Tables populated:
  - clob_markets         (market metadata: tick_size, taker_base_fee, ...)
  - clob_orderbook       (book snapshots)
  - clob_quotes          (best bid/ask/mid)
  - clob_prices_history  (hourly bars, used by derive_priors signal_mu)
  - clob_progress        (resume markers — do NOT truncate)

Usage: see `python -m src.ingest.clob_api --help`. Pass-through.
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 0 of 8 — Ingest CLOB API into ClickHouse")
    from data.sources.clob_api import main
    main()
