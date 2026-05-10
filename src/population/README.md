# `src/population/` — Step 3: Build agents from real Polymarket wallets

This is the methodological heart of the thesis. Every agent is
anchored to a real on-chain wallet that traded the target market
*before* the market opened (no resolution leakage). All
"hyperparameters" are deterministic functions of the data — see
`docs/EMPIRICAL_PRIORS.md` once Stage C lands.

| File | Purpose |
|---|---|
| `wallet_calibration.py` | Aggregate per-wallet trade history from `dataapi_trades` (v7: was live API in v4-v6) |
| `trade_history.py` | Polymarket CLOB-trades fetcher (v7: largely superseded by `dataapi_trades` table; kept for ad-hoc fills) |
| `persona_generator.py` | One LLM call per wallet → `profile_text` (no role labels; bio + display_name from `dataapi_holders` injected, sanitized) |
| `build_population.py` | Combine features + cached personas + private signals into `list[AgentInit]` consumed by the simulator |

## Public API

```python
from src.population.wallet_calibration import calibrate
from src.population.persona_generator import generate_for_market
from src.population.build_population import build_population, AgentInit
```

## Methodological commitments

- Cutoff = `min(trade_time)` from `dataapi_trades` for the target
  conditionId — exact market open. No 60-day fallback.
- Wallet inclusion: by data-driven percentile thresholds (see
  `docs/EMPIRICAL_PRIORS.md` once landed), not arbitrary `n_wallets`
  / `n_resolved_prior` constants.
- Private signal `μ` = first-24h volume-weighted average of
  `clob_prices_history` for the target token. `σ` derived from the
  empirical population accuracy distribution, not a magic 0.4.
- Persona prompt includes the wallet's `dataapi_holders.bio` and
  `display_name` (sanitized for role-label leakage). The LLM sees
  trader self-description plus pure-numerical features only.

See `tests/test_population_*.py` for the executable contract.
