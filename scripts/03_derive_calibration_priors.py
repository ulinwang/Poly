#!/usr/bin/env python3
"""Step 3 of 8 — Derive every simulator hyperparameter from the data.

Emits `data/priors_<slug>.json` containing:

  - market_open_ts, end_date         (from dataapi_trades + markets_resolved)
  - tick_size, taker_fee_bps         (from clob_markets)
  - n_ticks                          (market lifetime / 6h, clamped [8, 48])
  - signal_mu                        (first-24h VWAP; clob_prices_history → dataapi_trades fallback)
  - bootstrap.{anchor_yes, spread,
       depth_per_level, depth_levels} (clob_orderbook → dataapi_trades dispersion fallback)
  - winning_idx                      (for SERD validation later)

Re-running with the same DB state always produces the same JSON —
this is the v7 reproducibility commitment. See
`docs/EMPIRICAL_PRIORS.md` for the source SQL of every value.

Usage:
    python scripts/03_derive_calibration_priors.py --slug <chosen-slug>
    python scripts/03_derive_calibration_priors.py --slug <slug> --out-dir data/
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 3 of 8 — Derive calibration priors\n")
    from agent.features.market import main
    main()
