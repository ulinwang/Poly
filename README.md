# PolyMETL — v8

LLM-driven multi-agent simulation of Polymarket trader behavior,
calibrated from real on-chain wallet history. **Graduation thesis**
project; the codebase is organized as five top-level packages that
mirror the experimental flow:

```
data/         all ETL + ClickHouse access + read queries
agent/        features → personas → prompt → decision → memory
environment/  Gym-style CLOB env; only tools are visible to agents
experiments/  YAML config → run → output/<exp_id>/{raw,analysis,figure}
output/       per-experiment artifact trees
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full
dependency diagram + the strict no-direct-CH-from-agent rule.

## One command to reproduce a thesis run

```bash
uv sync                                              # one-time
clickhouse-client --query "CREATE DATABASE IF NOT EXISTS polymetl"

# Step A — ingest data layer (resumable, hours-days; one-time)
python -m data.sources.gamma_api.cli      # ~146k markets
python -m data.sources.clob_api.cli       # ~16M price-history bars
python -m data.sources.data_api.cli       # ~42M trades, 2.9M holders

# Step B — pick a market slug, build features + personas (~5 min)
python -m agent.features.market --slug <slug>     # priors JSON
python -m agent.features.wallet --slug <slug>     # wallet_features rows
python -m agent.personas.calibrated --target-market-id <condition_id>

# Step C — run the experiment from a YAML config (~75 min live)
python -m experiments run experiments/configs/exp001_baseline.yaml
# → output/<exp_id>/{meta.json, raw/*.parquet, analysis/, figure/}

# Step D — list / inspect prior runs
python -m experiments list
python -m experiments show <exp_id>
```

End-to-end recipe in [`docs/REPRODUCE.md`](docs/REPRODUCE.md).

## Module map

```
data/
├── sources/{clob_api,data_api,gamma_api,onchain}/{puller,schema,parsers,cli}.py
├── store/{clickhouse,config}.py + views/*.sql
├── query/{markets,trades,orderbook,prices,holders,wallets,onchain}.py
├── exports/, docs/, analysis/

agent/
├── features/{wallet,market,temporal,pipeline}.py
├── personas/{persona,calibrated,library}.py + templates/*.{txt,j2}
├── prompt/{builder,tokens}.py
├── decision/{types,llm,parser,retry,runtime}.py
├── memory/episodic.py
└── factory.py                  ← init_agents(slug)

environment/
├── env.py (PolyEnv), orderbook.py, ctf.py, fees.py, settlement.py
├── tools/{place_order,cancel_order,split_position,merge_position,
│            redeem,observe}.py
├── observers/{quote_only,tape,full_book}.py
└── seeders/{from_clob_history,from_holders}.py

experiments/
├── runner.py                   ← run_experiment(config_path)
├── config.py (pydantic), parquet_sink.py, cli.py
├── configs/exp001_baseline.yaml, exp002_calibrated.yaml
├── analysis/{serd,calibration,tables,pnl}.py
└── plots/{market_landscape,wallet_population,price_curve,
          role_quartiles,pnl_distribution,action_mix}.py + _shared.py
```

Each package has its own `README.md` covering public API and
methodological commitments (most are folded into the package
`__init__.py` docstrings in v8).

## Data layer (ClickHouse) — current row counts

| Table | Rows | Used by |
|---|---|---|
| `dataapi_trades` | 42,042,912 | features.wallet, query.trades |
| `clob_prices_history` | 16,075,541 | query.prices, features.market |
| `dataapi_holders` | 2,895,288 | query.holders, calibrated personas |
| `clob_orderbook` | 2,732,298 | query.orderbook, bootstrap priors |
| `clob_markets` | 1,050,851 | query.markets (slug → condition_id) |
| `markets_full` | 146,231 | source for `markets_resolved` view |
| `agent_*`, `serd_results` | per-sim | experiments.runner outputs |
| `onchain_*` | 0 (scaffold) | data.sources.onchain (v9 ingest) |

Live snapshot in [`docs/DATA_INVENTORY.md`](docs/DATA_INVENTORY.md).

## Methodological constraints

1. **No look-ahead leakage**: every wallet feature is filtered by
   `trade_time < market_open_ts` (= first observed trade in the
   target market). No future-information contamination.
2. **No role labels in initialization**: persona generator strips
   forbidden labels from BOTH LLM output AND the wallet's
   self-described bio. Roles must emerge from the network in step 6
   (SERD), not from initialization.
3. **No magic constants**: every "hyperparameter" the simulator
   consumes is in `data/priors_<slug>.json`, derived from SQL. The
   only constants in source are numerical safeguards (epsilon, price
   floor/cap) and the explicit rigor commitment of LLM temperature 0.
4. **Reproducible exp_id**: `<utc_ts>-<config_name>-<git_sha8>-<config_hash8>`.
   `meta.json` captures git sha + config snapshot + priors summary
   so any `output/<exp_id>/` is fully replayable.

## Setup

```bash
git clone <repo> polymetl && cd polymetl
uv sync
cp .env.example .env && $EDITOR .env  # set DEEPSEEK key + CH host
clickhouse-client --query "CREATE DATABASE IF NOT EXISTS polymetl"
uv run python -m unittest discover -s tests -t .   # ~240 tests
```

## Documentation

| File | Purpose |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | v8 module dependency diagram + the no-CH rule |
| [`docs/PAPER.md`](docs/PAPER.md) | 8-section thesis paper outline |
| [`docs/EMPIRICAL_PRIORS.md`](docs/EMPIRICAL_PRIORS.md) | Every prior + its source SQL |
| [`docs/REPRODUCE.md`](docs/REPRODUCE.md) | Step-by-step recipe |
| [`docs/DATA_INVENTORY.md`](docs/DATA_INVENTORY.md) | Tables, row counts, freshness |
| [`docs/EXPERIMENT_LOG.md`](docs/EXPERIMENT_LOG.md) | Run history + audit findings |
| [`docs/ANALYSES.md`](docs/ANALYSES.md) | Catalogue of analysis SQL |
| [`docs/V5_VALIDATION.md`](docs/V5_VALIDATION.md) | v5 engine-correctness sprint |
