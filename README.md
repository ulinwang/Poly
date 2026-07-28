# Poly

[![CI](https://github.com/ulinwang/Poly/actions/workflows/ci.yml/badge.svg)](https://github.com/ulinwang/Poly/actions/workflows/ci.yml)
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
Poly/                         ← git repo
├── apps/
│   ├── web/                  React 19 + Vite + Tailwind v4 frontend
│   └── server/               TypeScript Fastify backend (API + serves the SPA)
├── sim/                      Python simulation core
│   ├── agent/                personas, features, prompt, decision (LLM), memory
│   ├── environment/          PolyEnv CLOB engine, order book, tools, seeders
│   ├── runner/               runner_cli.py + runner_stream.py (spawned by server)
│   └── evaluation/           metrics + eval schema (macro/micro)
├── research/                 offline analysis (thesis pipeline)
│   ├── experiments/          batch runner, analysis, plots
│   └── comparison/  viz/  scripts/
├── data/                     ETL + query layer (ClickHouse optional) — shared pkg
├── legacy/                   deprecated old python webapp (kept for reference)
├── docker-compose.yml        frontend, backend, and ClickHouse services
├── pyproject.toml            Python deps (uv); multi-root packages (sim, research, .)
└── package.json              npm workspaces (apps/web, apps/server)
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
#    If uv tries to download its own Python and fails, use the system python:
#    uv venv --python python3 && uv pip install -e .
uv sync
uv pip install -e .

# 2. Node deps (install from the workspace root)
npm install

# 3. Configure
#    You MUST create .env and set at least one LLM key before running experiments.
cp .env.example .env        # set your LLM key(s); ClickHouse host is optional

# 4a. Dev (hot reload): two terminals
cd apps/server && npm run dev      # API + sim on http://localhost:8765
cd apps/web    && npm run dev      # Vite dev server on http://localhost:5173 (proxies /api → 8765)
# open http://localhost:5173

# 4b. Or production-style (server serves the built SPA)
npm run build:web
npm run build:server
cd apps/server && npm start        # open http://localhost:8765
```

### Run with Docker

```bash
# Create and configure environment first
cp .env.example .env
# edit .env and set at least one LLM key

# Generate the required production secrets once and store them in .env
export POLY_API_TOKEN="$(openssl rand -hex 32)"
export POLY_SECRET="$(openssl rand -hex 32)"
export POLYMETL_CLICKHOUSE_PASSWORD="$(openssl rand -hex 32)"
docker compose up --build --wait

# Frontend and proxied API -> http://localhost:8080
# Readiness check          -> http://localhost:8080/api/v1/health/ready
```

You can also set the provider, model, and API key at runtime in the **Settings**
page — no restart needed.

The production Compose stack publishes only nginx on port **8080**. The backend
and ClickHouse stay on private Compose networks; nginx proxies `/api` to the
backend. The backend runs as the non-root `node` user and stores SQLite,
checkpoints, and event logs in the `backend-data` named volume.

Health checks gate service startup in dependency order. Fastify emits structured
JSON request logs with generated request IDs and redacts authorization headers,
cookies, API keys, and tokens. Set `POLY_LOG_LEVEL` to adjust verbosity.

Run the complete build/start/health/non-root/network/shutdown smoke test with:

```bash
./scripts/compose-smoke.sh
```

> **Development ports** — Vite **5173**, Fastify **8765**. Production publishes
> nginx on **8080** only.

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
| `POLY_API_TOKEN` | operator bearer token; required in production, minimum 32 characters |
| `POLY_API_READ_TOKEN` | optional read-only bearer token for API clients, minimum 32 characters |
| `POLY_LOG_LEVEL` | structured backend log level (default `info`) |
| `POLY_MAX_EXPERIMENT_AGENTS` | maximum agents per experiment (default `100`) |
| `POLY_MAX_EXPERIMENT_TICKS` | maximum ticks per experiment (default `200`) |
| `POLY_MAX_ACTIVE_RUNS` | maximum concurrently active experiments (default `2`) |
| `POLY_LLM_ENDPOINT_ALLOWLIST` | comma-separated exact origins allowed for private or HTTP custom LLM endpoints |
| `POLYMETL_CLICKHOUSE_USER` | local/non-Compose ClickHouse user; Compose fixes this to `poly` |
| `POLYMETL_CLICKHOUSE_PASSWORD` | non-empty ClickHouse password required by Compose |
| `POLYMETL_CLICKHOUSE_DATABASE` | ClickHouse database (default `polymetl`) |

Experiment limits are enforced by the server. The web UI reads the effective
limits from `GET /api/v1/experiments/limits`, so operator overrides stay in sync
without requiring a separate frontend build.

Custom LLM endpoints must use HTTPS and resolve to public IP addresses by
default. To use an intentionally private endpoint such as a local model server,
allowlist its exact origin (for example,
`POLY_LLM_ENDPOINT_ALLOWLIST=http://host.docker.internal:11434`).

> Never commit `.env`.

ClickHouse ports are intentionally not published by the default stack. For
administration, prefer `docker compose exec clickhouse clickhouse-client`.
External publishing requires an explicit local Compose override and must retain
the non-default user and password.

### API authentication

Production mode fails closed unless `POLY_API_TOKEN` is configured. Generate a
high-entropy token with `openssl rand -hex 32`. The web UI prompts for it and
keeps it only in the current tab's `sessionStorage`; API and SSE requests send
it as `Authorization: Bearer <token>`. Tokens are never accepted in query
strings.

Market/event browsing and the static provider catalog remain public read-only
routes. Settings, keys, experiments and their history/SSE streams, provider
model discovery, agent introspection, and analysis require authentication. An
optional `POLY_API_READ_TOKEN` can access protected GET/HEAD routes but receives
HTTP 403 for mutations. Nginx forwards the `Authorization` header unchanged.

Development mode (`npm run dev` in `apps/server`) remains unauthenticated by
default; set `POLY_API_TOKEN` to opt in locally. Direct API clients use:

```bash
curl -H "Authorization: Bearer $POLY_API_TOKEN" \
  http://localhost:8765/api/v1/experiments
```

## Development

### Tests

```bash
# Backend (vitest)
cd apps/server && npm test && npm run lint

# Frontend (build + lint; vitest for hooks/stores)
cd apps/web && npm run build && npm run lint && npx vitest run
```

### Continuous integration

The [GitHub Actions workflow](.github/workflows/ci.yml) runs on every pull
request and every push to `master`. It installs the locked Node dependencies
with `npm ci`, caches npm downloads, and runs server lint/tests/build plus web
lint/build on Node.js 20. The two workspaces run as separate jobs so failures
are easier to identify. A path-filtered
[Compose smoke workflow](.github/workflows/compose-smoke.yml) also builds,
starts, health-checks, and tears down the production stack when deployment
files or backend sources change.

> The Python `sim/` packages keep their historical top-level import names
> (`import agent`, `environment`, `experiments`, `data`, `evaluation`, …) via a
> multi-root `pyproject` config — after moving Python files, re-run
> `uv pip install -e .` to refresh the editable install.

### REST API (`/api/v1`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/markets` | GET | List live markets (supports `q`, case-insensitive exact `category`, `live_only`, `limit`, `offset`) |
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
