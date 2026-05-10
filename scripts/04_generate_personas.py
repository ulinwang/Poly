#!/usr/bin/env python3
"""Step 4 of 8 — Generate per-wallet behavioral personas via DeepSeek.

For every row in `wallet_features` for the target market, call DeepSeek
once with: (capital, tx_count, asset diversity, past_accuracy, n_resolved,
optional sanitized bio + display_name from `dataapi_holders`). Cached
to `data/wallet_personas.json` so re-runs do not re-pay for LLM calls.

LLM `temperature=0.0` (v7 reproducibility commitment, see
`docs/EMPIRICAL_PRIORS.md`). Profile text is post-cleaned against
`FORBIDDEN_LABELS` regex; bios are sanitized BEFORE the LLM sees them
(prevents seeding role labels SERD is supposed to discover post-hoc).

Wall-clock: ~1-2 seconds per wallet. ~50 wallets = ~2 minutes.
Requires `POLYMETL_DEEPSEEK_API_KEY` in `.env`.

Usage:
    python scripts/04_generate_personas.py --target-market-id <condition_id>
    python scripts/04_generate_personas.py --target-market-id <cid> --force
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    print("Step 4 of 8 — Generate personas via DeepSeek\n")
    from src.population.persona_generator import main
    main()
