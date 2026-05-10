# `src/population/` — Step 3: Calibrate the agent population

v7. Everything in this package is a **deterministic function of
ClickHouse state** — no live API calls, no magic-number
hyperparameters. Every value the simulator consumes (cutoffs, signal
mu, signal sigma bounds, capital floor/cap, bootstrap orderbook,
tick size, taker fee, n_ticks) is derived from `dataapi_trades`,
`markets_resolved`, `clob_markets`, `clob_orderbook`,
`clob_prices_history`, or `dataapi_holders` and cached to a single
JSON file `data/priors_<slug>.json`. See
`docs/EMPIRICAL_PRIORS.md` for the SQL behind every prior.

| File | Purpose |
|---|---|
| `select_market.py` | Pick a target market by SQL criteria over `markets_resolved` + `dataapi_trades` |
| `wallet_features.py` | Aggregate per-wallet pre-event features from `dataapi_trades` (SQL only — replaces v4-v6 live API) |
| `derive_priors.py` | Emit `data/priors_<slug>.json` with every empirical hyperparameter |
| `persona_generator.py` | LLM-generated `profile_text` per wallet, with `dataapi_holders.bio` and `display_name` injected (sanitized against role labels) |
| `build_population.py` | Combine wallet_features + cached personas + priors → `list[AgentInit]` |

## Public API

```python
from src.population.select_market import list_candidates
from src.population.wallet_features import calibrate, compute_features
from src.population.derive_priors import derive_priors
from src.population.persona_generator import generate_for_market, sanitize_bio
from src.population.build_population import (
    build_population, build_population_from_priors, AgentInit,
)
```

## CLI

```bash
# Step 1: pick a market
python -m src.population.select_market --min-wallets 30
# Step 2: aggregate per-wallet features (SQL only)
python -m src.population.wallet_features --slug <slug>
# Step 3: derive every prior into one JSON
python -m src.population.derive_priors --slug <slug>
# Step 4: LLM-generate sanitized personas
python -m src.population.persona_generator --target-market-id <condition_id>
```

`build_population_from_priors(slug)` is the v7 entry the runner
calls. It loads `priors_<slug>.json`, computes empirical capital
floor/cap from this market's wallet population (5th and 95th
percentiles), and assembles the `list[AgentInit]`.

## Methodological commitments

1. **No look-ahead leakage**: every feature is computed from rows
   with `trade_time < min(trade_time)` of the target market. The
   cutoff comes from `derive_priors.market_open_ts()`.
2. **No role labels**: `persona_generator` strips
   `FORBIDDEN_LABELS` from both the LLM output AND the wallet's
   self-described `bio` (via `sanitize_bio`). This protects SERD
   validation — roles must emerge from the network, not from
   initialization labels.
3. **Reproducibility**: LLM `temperature=0.0` for personas
   (documented in `docs/EMPIRICAL_PRIORS.md`); priors JSON is fully
   deterministic given a CH snapshot.

See `tests/test_population_*.py` for the executable contract.
