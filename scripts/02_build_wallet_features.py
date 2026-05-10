#!/usr/bin/env python3
"""Step 2 of 8 — Build per-wallet pre-event behavioral fingerprints.

For every wallet that traded the target market, aggregate (in pure
SQL against `dataapi_trades` × `markets_resolved`) their pre-event
trade count, capital, asset diversity, and capital-weighted past
accuracy. Cutoff = first observed trade in the target market — strict
no-look-ahead invariant.

Output rows persisted to `polymetl.wallet_features`. Re-runs
overwrite per the ReplacingMergeTree.

Wall-clock: ~1-2 minutes for ~50 wallets (per-wallet past-accuracy
SQL dominates; could be batched later).

Usage:
    python scripts/02_build_wallet_features.py --slug <chosen-slug>
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 2 of 8 — Build wallet features\n")
    from agent.features.wallet import main
    main()
