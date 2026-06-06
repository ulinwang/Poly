# Poly

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*[中文文档 → README_CN.md](README_CN.md)*

## What is Poly?

Poly is a multi-agent simulation platform for prediction markets (e.g. Polymarket).
Autonomous trading agents — each driven by a large language model — trade in a
simulated central-limit order book, so researchers can study price formation,
trader-behavior emergence, and market dynamics under controlled, reproducible
conditions.

Key features:

* **LLM-powered agents** — each trader has a configurable persona, memory, and
  reasoning pipeline grounded in real on-chain wallet history.
* **Multi-provider via litellm** — one interface over OpenAI, DeepSeek, Kimi
  (Moonshot), xAI, Gemini, Mistral, Anthropic, and any OpenAI-compatible
  endpoint; pick the provider/model in the Settings page.
* **Empirically calibrated** — agent priors and population mixes derive from
  queries against real Polymarket trade/holder data.
* **Full CLOB simulation** — a Gym-style order-book environment with CTF
  mechanics, fees, and settlement.
* **Eval layer** — macro (market price) and micro (per-agent) metrics streamed
  live to the web UI and summarized into post-hoc scorecards.
* **Live web dashboard** — a React 19 SPA: browse markets → open a market → run
  an experiment → watch it tick in real time (SSE).

## Architecture

A monorepo with a clean split between the web app, the Python simulation core,
and the offline research pipeline:

```text
Poly/                         (outer folder)
├── polymetl/                 ← git repo
│   ├── apps/
│   │   ├── web/              React 19 + Vite + Tailwind v4 frontend
│   │   └── server/           TypeScript Fastify backend (API + serves the SPA)
│   ├── sim/                  Python simulation core
│   │   ├── agent/            personas, features, prompt, decision (LLM), memory
│   │   ├── environment/      PolyEnv CLOB engine, order book, tools, seeders
│   │   ├── runner/           runner_cli.py + runner_stream.py (spawned by server)
│   │   └── evaluation/       metrics + eval schema (macro/micro)
│   ├── research/             offline analysis (thesis pipeline)
│   │   ├── experiments/      batch runner, analysis, plots
│   │   ├── comparison/  viz/  scripts/
│   ├── data/                 ETL + query layer (ClickHouse optional) — shared pkg
│   ├── legacy/               deprecated old python webapp (kept for reference)
│   ├── pyproject.toml        Python deps (uv); multi-root packages (sim, research, .)
│   └── package.json          npm workspaces (apps/web, apps/server)
└── thesis/                   paper artifacts (docx / ppt / refs) — outside the repo
```

Data flow at runtime:

```text
React SPA (:5173 dev, served at :8765)
      │  REST /api/v1/*  +  SSE
      ▼
TS Fastify server (apps/server, :8765)
      │  spawns  .venv/bin/python3 sim/runner/runner_cli.py  (JSON over stdin/stdout)
      ▼
Python sim core (sim/runner → environment + agent → litellm)
      │  streams events: tick_started, agent_decision, tick_finished,
      │  tick_metrics, agent_snapshots, settled …
      ▼
relayed back over SSE to the live observation page
```

* **Frontend** — React 19, Vite 8, Tailwind CSS v4, Recharts, Zustand.
* **Backend** — TypeScript Fastify; better-sqlite3 for experiments/settings; SSE
  for live streaming; serves the built SPA.
* **Sim core** — Python; LLM calls routed through litellm; API keys passed in
  from the server (encrypted at rest, never returned to the browser).
* **Data** — ClickHouse (optional, historical Polymarket data) + SQLite
  (experiments, settings).

## Quick Start

### Prerequisites

* Node.js 20+
* Python 3.11+ with [`uv`](https://github.com/astral-sh/uv)
* An API key for at least one LLM provider (DeepSeek / OpenAI / Kimi / …)

### Run it

```bash
# 1. Python deps (creates .venv, installs the multi-root packages editable)
uv sync
uv pip install -e .

# 2. Node deps
cd apps/server && npm install
cd ../web && npm install
cd ../..

# 3. Configure
cp .env.example .env        # set your LLM key(s); ClickHouse host is optional

# 4a. Dev (hot reload): two terminals
cd apps/server && npm run dev      # API + sim on http://localhost:8765
cd apps/web    && npm run dev      # Vite dev server on http://localhost:5173 (proxies /api → 8765)
# open http://localhost:5173

# 4b. Or production-style (server serves the built SPA)
cd apps/web && npm run build
cd ../server && npm run dev        # open http://localhost:8765
```

You can also set the provider, model, and API key at runtime in the **Settings**
page — no restart needed.

> **Ports** — dev frontend **5173**, backend/API + production SPA **8765**.

## Configuration

Copy `.env.example` to `.env`. LLM keys can be set here or entered in the
Settings page (where they are encrypted at rest).

| Variable | Description |
|----------|-------------|
| `POLYMETL_DEEPSEEK_API_KEY` / `_BASE_URL` / `_MODEL` | DeepSeek (default) |
| `POLYMETL_KIMI_API_KEY` / `_BASE_URL` / `_MODEL` | Kimi (Moonshot) |
| `POLYMETL_OPENAI_API_KEY` | OpenAI |
| `POLY_SECRET` | master key for encrypting stored API keys (set in production) |
| `POLY_ROOT` | override repo root used when spawning the Python sim |
| `POLYMETL_CLICKHOUSE_*` | ClickHouse connection (optional) |

> Never commit `.env`.

## Development

### Tests

```bash
# Backend (vitest)
cd apps/server && npm test && npm run lint

# Frontend (build + lint; vitest for hooks/stores)
cd apps/web && npm run build && npm run lint && npx vitest run
```

> The Python `sim/` packages keep their historical top-level import names
> (`import agent`, `environment`, `experiments`, `data`, `evaluation`, …) via a
> multi-root `pyproject` config — after moving Python files, re-run
> `uv pip install -e .` to refresh the editable install.

### REST API (`/api/v1`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/markets` | GET | List live markets (supports `q`, `category`, `limit`, `offset`) |
| `/markets/:slug` | GET | Market detail (fetched by slug; includes `event_slug`) |
| `/experiments` | GET / POST | List / create-and-start experiments |
| `/experiments/:id` | GET | Experiment detail |
| `/experiments/:id/cancel` | POST | Cancel a run |
| `/experiments/:id/events` | GET | SSE stream of live simulation events |
| `/settings/api` | GET / PUT | LLM settings (key never returned; `api_key_set` flag) |
| `/settings/test` | POST | Test the LLM connection |
| `/providers` | GET | litellm provider/model catalog |

## License

[MIT](LICENSE).

## Acknowledgments

* **Polymarket** — for the public API and on-chain data behind the calibration layer.
* Originally developed for a graduation thesis on decentralized-finance trader
  behavior; the manuscript and figures live outside this codebase (`../thesis/`).

---

*Poly is an independent research project, not affiliated with or endorsed by Polymarket.*
