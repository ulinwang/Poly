#!/usr/bin/env python3
"""Step 6 of 8 — Run SERD post-hoc analysis on a completed sim.

Implements Gomez-Cram et al. 2026 (ICIS):
  1. Build maker→taker net-flow network from `agent_fills`.
  2. Compute s_in, s_out, R[i] = s_in / s_out per agent.
  3. Assign quartile roles: ApexPredator > UpperMeso > LowerMeso > Prey.
  4. Verify monotonic ROI ordering across roles (paper Tables 2/4).
  5. Compute ΔROI(SERD) - ΔROI(DBSCAN+KMeans baseline) (paper Table 5).

Filters: synthetic env-maker (`agent_id = 999_999`) and self-loops
(maker == taker) are excluded from the network.

Usage:
    python scripts/06_analyze_serd.py --sim-id <hex>
    python scripts/06_analyze_serd.py --sim-id <hex> --pool-with <other-id> ...
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 6 of 8 — SERD analysis\n")
    from src.analysis.serd import main
    main()
