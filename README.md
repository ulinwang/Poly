# PolyMetl

[![Build Status](https://img.shields.io/badge/build-TBD-blue)](https://github.com/username/polymetl/actions)
[![Tests](https://img.shields.io/badge/tests-TBD-blue)](https://github.com/username/polymetl/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What is PolyMetl?

PolyMetl is an agent-based simulation platform for prediction markets (e.g., Polymarket). It simulates autonomous trading agents whose decisions are powered by large language models (LLMs), allowing researchers to study market dynamics, trader behavior emergence, and price formation under controlled, reproducible conditions.

Key features:

* **LLM-Powered Agents** — Each trader is an autonomous agent with a configurable persona, memory, and reasoning pipeline grounded in real on-chain wallet history.
* **Empirically Calibrated** — Agent priors and population mixes are derived from SQL queries against real Polymarket trade and holder data (no hand-tuned magic constants).
* **Full CLOB Simulation** — Gym-style central-limit order book environment with CTF mechanics, fees, settlement, and multiple observation modes.
* **Reproducible Experiments** — YAML-driven experiment configs produce fully traceable output trees with deterministic `exp_id` naming.
* **Live Web Dashboard** — React 19 frontend with real-time SSE streaming of simulation ticks, market explorer, and experiment management UI.
* **Modular Architecture** — Strict package boundaries (data / agent / environment / experiments) prevent look-ahead leakage and enforce clean dependencies.

> **Screenshot placeholder** — *Add a dashboard screenshot here once the UI is finalized.*

## Architecture

```text
+------------------+       +------------------+       +------------------+
|   experiments/   |       |   backend/       |       |  webapp/frontend |
|   runner.py      |       |   Fastify + SSE  |       |  React 19 SPA    |
|   parquet_sink   |       |   SQLite + TS    |       |  Vite + Tailwind |
|   analysis/      |       |                  |       |  Zustand + Charts|
+--------+---------+       +--------+---------+       +--------+---------+
         |                          |                          |
    reads features            serves API                 live tick UI
    writes parquet            spawns Python              market explorer
         |                     runner via CLI             experiment mgr
+--------v---------+          +--------v---------+        +--------v---------+
|     agent/       |          |  webapp/runner_  |        |   environment/   |
|  factory.py      |          |   stream.py      |        |  PolyEnv (CLOB)  |
|  features/*.py   |          |   (LLM sim core) |        |  orderbook.py    |
|  personas/*.py   |          +------------------+        |  tools/*.py      |
|  prompt/*.py     |                                      |  observers/*.py  |
|  decision/*.py   |                                      |  ctf/fees/settle |
|  memory/*.py     |                                      |  seeders/*.py    |
+--------+---------+                                      +--------+---------+
         |                                                         |
         |              data.query.* only                          |  priors
         +---------------------------+-----------------------------+
                                     |
                          +----------v----------+
                          |       data/         |
                          |  sources/{gamma_api,|
                          |          clob_api,  |
                          |          data_api}  |
                          |  store/clickhouse   |
                          |  query/*.py         |
                          +----------+----------+
                                     |
                          +----------v----------+
                          |    ClickHouse DB    |
                          |  (canonical market  |
                          |   + trade data)     |
                          +---------------------+
```

* **Frontend** — React 19 + Vite + Tailwind CSS + Recharts + Zustand
* **Backend** — TypeScript Fastify with modular routers, SQLite persistence, and Server-Sent Events (SSE) for live simulation streaming
* **Simulation Core** — Python LLM agents with configurable personas, empirically calibrated from real wallet behavior; spawned via CLI wrapper from the TS backend
* **Data Layer** — ClickHouse (historical Polymarket data, optional) + SQLite (experiments, settings, results)
* **Provider Support** — DeepSeek (default), Kimi (Moonshot), OpenAI, Anthropic, and any OpenAI-compatible custom endpoint

## Quick Start

### Prerequisites

* Node.js 20+
* Python 3.12+ (with `uv` recommended)
* ClickHouse (local or remote) for historical data ingestion
* A DeepSeek or OpenAI API key for LLM-powered agent decisions

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/username/polymetl.git
cd polymetl
docker-compose up
```

*Access the dashboard at `http://localhost:80`* (frontend nginx proxies `/api` to backend on `:8000`)

### Option 2: Manual

```bash
# 1. Clone & install Python dependencies
uv sync
# or: pip install -e .

# 2. Install Node.js dependencies
cd backend && npm install
cd ../webapp/frontend && npm install

# 3. Configure environment
cp .env.example .env
# Edit .env — set your LLM API key and ClickHouse host (optional)

# 4. Build the frontend
cd webapp/frontend
npm run build

# 5. Start the TypeScript backend (from project root)
cd backend
npm run dev          # dev mode with hot reload (port 8765)
# or: npm run build && npm start   # production mode

# 6. Open the dashboard
open http://localhost:8765
```

*The TS backend serves the built frontend statically and proxies API requests. No separate frontend dev server is required in production.*

## Configuration

Copy `.env.example` to `.env` and fill in the required values.

| Variable | Description | Example |
|----------|-------------|---------|
| `POLYMETL_DEEPSEEK_API_KEY` | DeepSeek API key (default) | `sk-...` |
| `POLYMETL_KIMI_API_KEY` | Kimi (Moonshot) API key | `sk-...` |
| `POLYMETL_OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `POLYMETL_DEEPSEEK_BASE_URL` | DeepSeek-compatible endpoint | `https://api.deepseek.com/v1` |
| `POLYMETL_KIMI_BASE_URL` | Kimi-compatible endpoint | `https://api.moonshot.cn/v1` |
| `POLYMETL_DEEPSEEK_MODEL` | Default model for agent decisions | `deepseek-v4-flash` |
| `POLYMETL_KIMI_MODEL` | Default Kimi model | `moonshot-v1-8k` |
| `POLYMETL_CLICKHOUSE_HOST` | ClickHouse host (optional) | `localhost` |
| `POLYMETL_CLICKHOUSE_PORT` | ClickHouse native port | `9000` |
| `POLYMETL_CLICKHOUSE_USER` | ClickHouse user | `default` |
| `POLYMETL_CLICKHOUSE_PASSWORD` | ClickHouse password | *(empty)* |
| `POLYMETL_CLICKHOUSE_DATABASE` | ClickHouse database name | `polymetl` |
| `POLYMETL_RPC_URL` | Polygon RPC for on-chain data | `https://1rpc.io/matic` |

> **Provider selection at runtime** — The web dashboard's Settings page lets you switch between DeepSeek, Kimi, OpenAI, Anthropic, or any custom OpenAI-compatible endpoint without restarting the server.

> **Security note** — Never commit `.env`. The `.env.example` file contains only safe defaults.

## Development

### Project Structure

```text
polymetl/
├── backend/             # TypeScript Fastify backend (NEW)
│   ├── src/
│   │   ├── server.ts    # Fastify app factory
│   │   ├── routes/      # markets, experiments, settings, providers
│   │   ├── services/    # Polymarket API fetcher, runner spawner
│   │   ├── db/          # better-sqlite3 persistence
│   │   └── types/       # Shared TypeScript interfaces
│   ├── Dockerfile       # TS backend container image
│   └── tests/           # Vitest unit + integration tests
├── data/                # ETL pipelines, ClickHouse schemas, query layer
│   ├── sources/         # API pullers (Gamma, CLOB, Data API)
│   ├── store/           # ClickHouse + config connections
│   ├── query/           # Canonical read-only queries
│   └── exports/         # Data export utilities
├── agent/               # Agent lifecycle: features, personas, prompt, LLM decision
│   ├── features/        # Wallet + market feature engineering
│   ├── personas/        # Persona generation (calibrated, archetype, random)
│   ├── prompt/          # Prompt builder + token accounting
│   ├── decision/        # LLM call loop, parsing, retry logic
│   ├── memory/          # Episodic memory
│   └── factory.py       # init_agents(slug)
├── environment/         # CLOB simulation engine
│   ├── env.py           # PolyEnv (Gym-style interface)
│   ├── orderbook.py     # Limit-order book implementation
│   ├── tools/           # Agent-facing actions (place, cancel, split, merge, redeem, observe)
│   ├── observers/       # Observation modes (quote-only, tape, full book)
│   └── seeders/         # Bootstrap orderbook from historical data
├── experiments/         # Experiment runner, analysis, plotting
│   ├── runner.py        # YAML-driven experiment orchestration
│   ├── config.py        # Pydantic config validation
│   ├── configs/         # YAML experiment definitions
│   ├── analysis/        # Post-hoc metrics + SERD clustering
│   └── plots/           # Matplotlib / Plotly figure generation
├── webapp/              # Full-stack dashboard
│   ├── runner_stream.py # Python simulation streaming entry point
│   ├── runner_cli.py    # CLI wrapper (stdin JSON → stdout JSONL events)
│   ├── backend/         # Legacy FastAPI server (deprecated, kept for reference)
│   └── frontend/        # React 19 SPA
│       ├── src/pages/   # Dashboard, Market Explorer, Experiment Builder
│       ├── src/components/
│       └── src/stores/  # Zustand state management
├── tests/               # Python unit + integration tests
├── output/              # Per-experiment artifact trees (gitignored, see ../thesis-assets/)
└── docs/                # Thesis manuscripts (gitignored, see ../thesis-assets/)
```

### Running Tests

```bash
# TypeScript backend tests (vitest)
cd backend
npm test

# Python tests (~240 tests)
python -m unittest discover -s tests -t .
# Or with uv
uv run python -m unittest discover -s tests -t .
```

### Adding New Agent Personas

1. Create a new persona generator under `agent/personas/` (e.g., `my_persona.py`).
2. Implement the persona-building logic (see `calibrated.py` or `archetype.py` for reference).
3. Register it in `agent/personas/library.py`.
4. Add a corresponding YAML config under `experiments/configs/` referencing the new persona set.
5. Run the experiment: `python -m experiments run experiments/configs/my_exp.yaml`

## Deployment

### Docker

`docker-compose.yml` orchestrates two services:

* `frontend` — Nginx serving the built React SPA (`webapp/frontend/dist`)
* `backend` — TypeScript Fastify server (`backend/Dockerfile`)

Build and run:

```bash
# 1. Build frontend first (needed by backend static file serving)
cd webapp/frontend && npm install && npm run build

# 2. Start everything
cd ../..
docker-compose up
```

The backend container:
- Serves API on port `8000`
- Serves built frontend SPA with fallback to `index.html`
- Persists SQLite data via volume mount `./backend/data:/app/backend/data`

### Environment-Specific Configs

* `.env` — local development overrides
* Production secrets should be injected via Docker secrets, K8s config maps, or your cloud provider's secret manager (never committed to the repo).

## API Documentation

The backend exposes a REST API under `/api/v1`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/settings/api` | `GET` / `PUT` | Read / update LLM provider settings |
| `/api/v1/settings/general` | `GET` / `PUT` | Read / update general app settings |
| `/api/v1/markets` | `GET` | List live Polymarket markets |
| `/api/v1/markets/{slug}` | `GET` | Get market details by slug |
| `/api/v1/markets/categories` | `GET` | List market categories |
| `/api/v1/experiments` | `GET` | List all experiments |
| `/api/v1/experiments` | `POST` | Create and start a new experiment |
| `/api/v1/experiments/{id}` | `GET` | Get experiment details |
| `/api/v1/experiments/{id}/cancel` | `POST` | Cancel a running experiment |
| `/api/v1/experiments/{id}/stream` | `GET` | SSE stream of live simulation ticks |
| `/api/v1/experiments/search` | `GET` | Search experiments by query string |

Interactive docs (Swagger UI) are available at `/docs` when the backend is running.

## Contributing

Contributions are welcome! Please open an issue first to discuss significant changes.

1. **Fork** the repository and create a feature branch (`git checkout -b feat/my-feature`).
2. **Code style** — Follow PEP 8 for Python and the existing Prettier/ESLint config for TypeScript/React. Keep changes minimal and focused.
3. **Tests** — Add or update tests for any new functionality. Ensure the existing test suite passes.
4. **Documentation** — Update `docs/` and this README if your change affects architecture, setup, or public APIs.
5. **Pull Request** — Open a PR with a clear description, referencing any related issues. PRs require at least one review before merge.

## License

This project is licensed under the [MIT License](LICENSE).

## Acknowledgments

* **Polymarket** — For providing the public API and on-chain data that powers the empirical calibration layer.
* **Academic context** — This software was originally developed as part of a graduation thesis on decentralized finance trader behavior. The thesis manuscript, figures, and defense materials are maintained in a separate repository and are not part of this open-source codebase.

---

*PolyMetl is an independent research project and is not affiliated with or endorsed by Polymarket.*
