#!/usr/bin/env python3
"""Step 0 of 8 — Ingest Polymarket data-api endpoints into ClickHouse.

Calls `src/ingest/data_api.py`. Per-market trade history (~42M rows
at last count) and per-wallet holdings + bios (~2.9M rows) — these
are the v7 backbone, used by every later step.

Tables populated:
  - dataapi_trades   (price/size/wallet per trade)
  - dataapi_holders  (display_name + bio per wallet — consumed by persona_generator)
  - dataapi_oi       (open interest snapshots)
  - dataapi_progress (resume markers — do NOT truncate)

Usage: see `python -m src.ingest.data_api --help`. Pass-through.
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 0 of 8 — Ingest data-api into ClickHouse")
    from src.ingest.data_api import main
    main()
