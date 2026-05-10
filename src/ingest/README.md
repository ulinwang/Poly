# `src/ingest/` — Step 0: Polymarket data ingestion

ETL modules that pull Polymarket's public APIs into ClickHouse. Run
**once per data source** (or on a cron) to keep the DB in sync; the
rest of the pipeline (steps 1–6) reads from the DB exclusively.

| Module | Endpoint | ClickHouse table(s) | Run |
|---|---|---|---|
| `clob_api.py` | `clob.polymarket.com` | `clob_markets`, `clob_prices_history`, `clob_orderbook`, `clob_quotes`, `clob_progress` | `python -m src.ingest.clob_api --endpoint all` |
| `data_api.py` | `data-api.polymarket.com` | `dataapi_trades`, `dataapi_holders`, `dataapi_oi`, `dataapi_progress` | `python -m src.ingest.data_api --endpoint all --workers 30` |
| `gamma_full.py` | `gamma-api.polymarket.com` | `markets_full` | `python -m src.ingest.gamma_full --closed all` |

All three are resumable: per-(endpoint, key) progress is tracked so
re-runs skip already-processed markets.

## Why these are step 0

Steps 1-6 of the thesis pipeline (simulator, agent, population,
sim-data-collection, plotting, paper) all consume rows from
ClickHouse — never from a live API. Decoupling ingest cleanly lets us
freeze the dataset before each experiment for reproducibility.

The user wrote these modules; v7 only **moved** them from top-level
`src/*.py` into this package and updated the `from .clickhouse_client`
imports to `from ..pipeline.clickhouse`. The ingest *logic* is
unchanged.

## See also

- `docs/DATA_INVENTORY.md` — current row counts per table.
- `scripts/00_ingest_*.py` — thin wrappers around these modules
  for the numbered-pipeline UX.
