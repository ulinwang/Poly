# PolyMETL — v7

LLM-driven multi-agent simulation of Polymarket trader behavior,
calibrated from real on-chain wallet history. **Graduation thesis**
project; the codebase is organized to be scientifically rigorous and
reproducible:

- Every "hyperparameter" is a deterministic function of ClickHouse
  state — see [`docs/EMPIRICAL_PRIORS.md`](docs/EMPIRICAL_PRIORS.md).
- LLM `temperature = 0.0` for both persona generation and trader
  decisions — the only externally-stochastic component is the LLM
  endpoint itself.
- Pipeline is laid out as 8 numbered scripts in `scripts/` so the
  experimental flow is obvious from the directory listing.

## The 8-step pipeline

| Step | Script | What it does |
|---|---|---|
| **0** | `00_ingest_{clob,dataapi,gamma}.py` | Populate ClickHouse from Polymarket APIs (resumable; run once) |
| **1** | `01_select_target_market.py` | SQL-pick a resolved binary market matching criteria |
| **2** | `02_build_wallet_features.py` | Aggregate per-wallet pre-event features (SQL only, no live API) |
| **3** | `03_derive_calibration_priors.py` | Emit `data/priors_<slug>.json` with every empirical hyperparameter |
| **4** | `04_generate_personas.py` | LLM-generate sanitized persona text per wallet (with bio + display_name from `dataapi_holders`) |
| **5** | `05_run_simulation.py` | Run multi-agent CLOB sim; persist actions / fills / positions |
| **6** | `06_analyze_serd.py` | SERD post-hoc validation (Gomez-Cram et al. 2026) |
| **7** | `07_render_figures.py` | 6 paper figures → `figures/{png,pdf}` |
| **8** | `08_render_tables.py` | 4 paper tables → `tables/{md,tex}` |

End-to-end commands are in
[`scripts/README.md`](scripts/README.md) (one-target-market reference
flow at the bottom).

## Module map

```
src/
├── ingest/       Step 0 — user-authored ETL (clob_api, data_api, gamma_full)
├── core/         Sim engine: CLOB orderbook, env, lifecycle
├── agent/        Persona dataclass, decision LLM client
├── population/   Step 1-4: market selection, wallet features, priors,
│                            persona generation, build_population
├── pipeline/     Step 5: runner.py orchestrates one sim run; ClickHouse client
├── analysis/     Step 6-7: SERD, sim-vs-real comparison, plots
└── thesis/       Step 8: paper tables (md + LaTeX)
```

Each package has a one-page `README.md` covering its public API and
methodological commitments.

## Data layer (ClickHouse)

| Table | Rows | Source / role |
|---|---|---|
| `markets_full` | ~146k | Gamma full payload (~125 fields) |
| `markets_resolved` | (view) | Resolved-only filter on `markets_full` |
| `clob_markets` | ~1.05M | CLOB `/markets` (tick_size, taker_base_fee, neg_risk, ...) |
| `clob_orderbook` | ~2.7M | Book snapshots (bootstrap-depth source) |
| `clob_quotes` | ~103k | Best bid/ask/mid snapshots |
| `clob_prices_history` | ~10M | Hourly CLOB bars (signal_mu primary source) |
| `dataapi_trades` | ~42M | Per-trade resolution (signal_mu / wallet feature backbone) |
| `dataapi_holders` | ~2.9M | Bio + display_name per wallet (persona input) |
| `dataapi_oi` | ~113k | Open-interest snapshots |
| `wallet_features` | small | Step 2 output |
| `agent_simulations`, `agent_actions`, `agent_fills`, `agent_positions`, `agent_personas`, `serd_results` | small | Step 5 + 6 outputs |

Schema details and row counts live in
[`docs/DATA_INVENTORY.md`](docs/DATA_INVENTORY.md).

## Setup

```bash
git clone <repo>
cd polymetl
uv sync                                   # installs everything in pyproject.toml
cp .env.example .env && $EDITOR .env      # fill DEEPSEEK key + CH host
clickhouse-client --query "CREATE DATABASE IF NOT EXISTS polymetl"
uv run python -m unittest discover tests  # ~140 tests should pass
```

## Reproducing the thesis run

See [`docs/REPRODUCE.md`](docs/REPRODUCE.md). The default reference
market is `will-the-chopsticks-catch-spacex-starship-flight-test-11-superheavy-booster`
(SpaceX flight test; resolved NO).

## Methodological constraints

1. **No look-ahead leakage**: every feature query is filtered by
   `trade_time < market_open_ts`, where `market_open_ts =
   min(trade_time)` of the target market.
2. **No role labels in initialization**: `persona_generator.py`
   strips `FORBIDDEN_LABELS` from BOTH the LLM output AND the
   wallet's self-described `bio` (via `sanitize_bio`). Roles must
   emerge from the network in step 6 (SERD), not from initialization.
3. **No magic constants**: every "hyperparameter" the simulator
   consumes is in `data/priors_<slug>.json`, derived from SQL. The
   only constants in `src/` are numerical safeguards (epsilon, price
   floor/cap) and the explicit rigor commitment of LLM temperature 0.

## Documentation

| File | Purpose |
|---|---|
| [`docs/PAPER.md`](docs/PAPER.md) | Thesis paper outline (8 sections) |
| [`docs/EMPIRICAL_PRIORS.md`](docs/EMPIRICAL_PRIORS.md) | Every prior + its source SQL + the few explicit constants |
| [`docs/REPRODUCE.md`](docs/REPRODUCE.md) | Step-by-step reproduction recipe |
| [`docs/DATA_INVENTORY.md`](docs/DATA_INVENTORY.md) | Tables, row counts, freshness |
| [`docs/EXPERIMENT_LOG.md`](docs/EXPERIMENT_LOG.md) | Run history + audit findings |
| [`docs/ANALYSES.md`](docs/ANALYSES.md) | Catalogue of analysis SQL |
| [`docs/V5_VALIDATION.md`](docs/V5_VALIDATION.md) | v5 engine-correctness sprint |
