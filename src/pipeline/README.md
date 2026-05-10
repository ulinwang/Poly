# `src/pipeline/` — Step 4: Orchestration + sim data collection

The runner that wires steps 1+2+3 together, executes a simulation,
and persists every action / fill / position to ClickHouse.

| File | Purpose |
|---|---|
| `runner.py` | `main()` CLI; loads market + population, builds `Simulation`, calls `core.env.run_simulation`, settles, writes to DB |
| `clickhouse.py` | `ClickHouse` wrapper class with all the v3-v5 sim schema DDLs and insert helpers |
| `config.py` | `Settings` (pydantic) — env-var-backed configuration: ClickHouse host/port, DeepSeek key/model/timeout, signal-sigma bounds, capital floor/cap (kept as defaults; v7 priors override per-market) |
| `__main__.py` | `python -m src.pipeline ...` thin entry point |

## Public API

```python
from src.pipeline.clickhouse import ClickHouse
from src.pipeline.config import get_settings, Settings
from src.pipeline.runner import main as run_pipeline
```

## CLI

```bash
# Recommended (v7): use the numbered scripts in scripts/, which call
# this runner under the hood after preparing the priors JSON.
python scripts/05_run_simulation.py --slug <chosen>

# Direct (low-level):
python -m src.pipeline --slug <slug> --population calibrated \
    --n-ticks 24 --seed-liquidity --skip-clob \
    --notes "ad-hoc run"
```

## What gets persisted per sim run

- 1 row in `agent_simulations` (sim_id, market_id, n_agents, n_ticks,
  engine_param, started_at, ended_at, final_sim_yes_price, notes)
- N rows in `agent_personas` (one per calibrated agent)
- N×T rows in `agent_actions` (every tick's action + LLM raw response)
- ≥0 rows in `agent_fills` (every cleared trade)
- N×T rows in `agent_positions` (cash + reserved + inventory snapshot)

Rerun-safe: each sim gets a UUID-derived `sim_id`; queries filter on
that.
