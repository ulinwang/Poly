#!/usr/bin/env python3
"""Step 1 of 8 — Select a target market for the simulation.

Lists candidate resolved markets matching the criteria (volume range,
minimum unique wallets, optional date window). The top row by wallet
count is your `--slug` for steps 2-8.

Default criteria match the v4 paper: a single-event binary YES/NO
market with at least 30 unique wallet participants and a manageable
volume range ($5K-$5M) so calibration finishes in reasonable time.

Usage:
    python scripts/01_select_target_market.py --min-wallets 30
    python scripts/01_select_target_market.py --min-volume 10000 \\
        --max-volume 100000 --end-after 2025-09-01

See also: `python -m src.population.select_market --help` for the
underlying CLI.
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 1 of 8 — Select target market\n")
    from src.population.select_market import main
    main()
