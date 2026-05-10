# `scripts/` — numbered v7 pipeline (steps 0-8)

Run scripts in numerical order. Each script is a thin wrapper over a
`src/` module; the underlying CLI is `python -m src.<package>.<module>`.

| Step | Script | Wrapped module | Typical wall-clock |
|---|---|---|---|
| 0 | `00_ingest_clob.py` | `src.ingest.clob_api` | days (resumable) |
| 0 | `00_ingest_dataapi.py` | `src.ingest.data_api` | hours-days (resumable) |
| 0 | `00_ingest_gamma.py` | `src.ingest.gamma_full` | ~1 hour |
| 1 | `01_select_target_market.py` | `src.population.select_market` | ~10 s |
| 2 | `02_build_wallet_features.py` | `src.population.wallet_features` | 1-2 min per market |
| 3 | `03_derive_calibration_priors.py` | `src.population.derive_priors` | ~1 s |
| 4 | `04_generate_personas.py` | `src.population.persona_generator` | ~2 min per market (DeepSeek) |
| 5 | `05_run_simulation.py` | `src.pipeline.runner` | ~75 min per sim (DeepSeek) |
| 6 | `06_analyze_serd.py` | `src.analysis.serd` | ~1 s |
| 7 | `07_render_figures.py` | `src.analysis.plots` | ~10 s |
| 8 | `08_render_tables.py` | `src.thesis.tables` | ~1 s |

## Prereqs

- ClickHouse running locally (default `localhost:9000`, db `polymetl`).
- `.env` populated (see `polymetl/pipeline/config.py:Settings`):
  - `POLYMETL_DEEPSEEK_API_KEY` (required for steps 4 + 5)
  - `POLYMETL_CLICKHOUSE_HOST`, `POLYMETL_CLICKHOUSE_PORT`, etc.
- Step 0 must complete (or be partially populated) before step 1 has
  any markets to choose from.

## End-to-end (one-target-market reference flow)

```bash
# ONE-TIME: ingest data layer (resumable, can run in background)
python scripts/00_ingest_gamma.py
python scripts/00_ingest_clob.py
python scripts/00_ingest_dataapi.py

# PER-EXPERIMENT: pick one slug and run the chain
SLUG=$(python scripts/01_select_target_market.py --min-wallets 30 \
       | grep '^Top pick' | awk '{print $NF}')

python scripts/02_build_wallet_features.py --slug "$SLUG"
python scripts/03_derive_calibration_priors.py --slug "$SLUG"
# Pull condition_id out of the priors JSON for step 4
CID=$(python -c "import json; print(json.load(open('data/priors_'+'$SLUG'+'.json'))['condition_id'])")
python scripts/04_generate_personas.py --target-market-id "$CID"

python scripts/05_run_simulation.py --slug "$SLUG" --seed-liquidity \
       --notes "v7 reference run"

# Read sim_id from the runner log, then:
python scripts/06_analyze_serd.py --sim-id <sim_id>
python scripts/07_render_figures.py --slug "$SLUG" --sim-id <sim_id>
python scripts/08_render_tables.py --slug "$SLUG" --sim-id <sim_id>
```

## Other helpers (not numbered)

These pre-date v7 and remain because they're handy:

- `inspect_market_fields.py`, `top_active_markets.py`: ad-hoc Gamma probes.
- `build_*_pdf.py`: data-dictionary PDF builders.
- `export_*_csv.py`: CSV exporters.
- `sql/`: hand-written analysis queries.
