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
# 1. Locked Python deps (creates .venv, installs multi-root packages editable)
#    If uv cannot download the pinned Python, use an installed Python 3.11+:
#    uv sync --frozen --python python3
uv sync --frozen

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
| `POLYMETL_LANGFUSE_PROMPT_MANAGEMENT_ENABLED` | optional managed prompt lookup; local v1 remains the fallback |
| `POLYMETL_LANGFUSE_PUBLIC_KEY` / `_SECRET_KEY` / `_BASE_URL` | Langfuse Cloud or self-hosted connection |
| `POLYMETL_LANGFUSE_PROMPT_LABEL` / `_CACHE_TTL_SECONDS` | managed prompt rollout label and SDK cache TTL |
| `POLYMETL_LANGFUSE_ENABLED` | optional Langfuse Agent Loop tracing; disabled by default |
| `POLYMETL_LANGFUSE_ENVIRONMENT` / `_RELEASE` / `_SAMPLE_RATE` | trace deployment identity and sampling |
| `POLYMETL_LANGFUSE_CAPTURE_POLICY` | `metadata` (safe default) or `full` visible prompt/output capture |
| `POLY_SECRET` | master key for encrypting stored API keys (set in production) |
| `POLY_ROOT` | override repo root used when spawning the Python sim |
| `POLY_API_TOKEN` | operator bearer token; required in production, minimum 32 characters |
| `POLY_API_READ_TOKEN` | optional read-only bearer token for API clients, minimum 32 characters |
| `POLY_LOG_LEVEL` | structured backend log level (default `info`) |
| `POLY_MAX_EXPERIMENT_AGENTS` | maximum agents per experiment (default `100`) |
| `POLY_MAX_EXPERIMENT_TICKS` | maximum ticks per experiment (default `200`) |
| `POLY_MAX_ACTIVE_RUNS` | maximum concurrently active experiments (default `2`) |
| `POLY_EVENT_LOG_MAX_BYTES` | maximum durable event log size per run (default `67108864`, 64 MiB) |
| `POLY_EVENT_LOG_MAX_PENDING_BYTES` | maximum in-memory async event-write queue per run (default `4194304`, 4 MiB) |
| `POLY_EVENT_LOG_RETENTION_DAYS` | event-log retention window (default `30`) |
| `POLY_CHECKPOINT_MAX_BYTES` | maximum resumable checkpoint size (default `134217728`, 128 MiB) |
| `POLY_CHECKPOINT_RETENTION_DAYS` | checkpoint retention window (default `30`) |
| `POLY_REPLAY_DEFAULT_LIMIT` | default events returned by one replay page (default `1000`) |
| `POLY_REPLAY_MAX_LIMIT` | maximum events returned by one replay page (default `5000`) |
| `POLY_LLM_ENDPOINT_ALLOWLIST` | comma-separated exact origins allowed for private or HTTP custom LLM endpoints |
| `POLYMETL_CLICKHOUSE_USER` | local/non-Compose ClickHouse user; Compose fixes this to `poly` |
| `POLYMETL_CLICKHOUSE_PASSWORD` | non-empty ClickHouse password required by Compose |

### Optional Langfuse LLMOps

Poly resolves every system, state, belief-stage, and trade-stage prompt through
a versioned registry. Repository template v1 is the default and guaranteed
fallback, so prompt service failures never fail an agent tick. Every Decision
and generation lifecycle event records source, name, version/label, SHA-256
content hash, language, and render variables; public runner introspection
exposes the identity and variable names without credentials or prompt content.

To install prompt management and tracing support:

```bash
uv sync --extra prompt-management --extra observability
```

Configure the shared `POLYMETL_LANGFUSE_*` connection variables shown in
`.env.example`. Set `POLYMETL_LANGFUSE_PROMPT_MANAGEMENT_ENABLED=true` for
managed prompts. The expected text prompt
names are `poly/clob-system/{en,zh}`, `poly/user-state/{en,zh}`,
`poly/belief-stage/{en,zh}`, and `poly/trade-stage/{en,zh}`. The selected
managed prompt object is linked directly to the matching Langfuse generation
when tracing is also enabled.

See `sim/agent/prompt/README.md` for rollout and fallback details.

Set `POLYMETL_LANGFUSE_ENABLED=true` to record each simulation as
`experiment → tick → agent loop → generation/tool`.

Traces include simulation/decision identity, persona and
budget metadata, model, latency, token usage, prompt placeholder identity, and
errors. Telemetry is fail-open: a missing SDK, missing credentials, exporter
outage, or flush timeout never changes simulation behavior.

`metadata` is the recommended capture policy and omits prompt, message, tool
argument, search result, and model-output content. `full` includes visible
inputs/outputs after secret redaction; hidden provider reasoning and raw
responses are never exported. Review your data policy before enabling `full`,
especially when using Langfuse Cloud. For self-hosted Langfuse, change
`POLYMETL_LANGFUSE_BASE_URL` to your HTTPS endpoint. See
`sim/observability/README.md` for the full configuration and lifecycle map.
| `POLYMETL_CLICKHOUSE_DATABASE` | ClickHouse database (default `polymetl`) |

Experiment limits are enforced by the server. The web UI reads the effective
limits from `GET /api/v1/experiments/limits`, so operator overrides stay in sync
without requiring a separate frontend build.

Event logs are written by an ordered asynchronous writer. If storage fails or a
configured byte bound is reached, the run continues and `event_persistence` on
the experiment detail reports the degraded/limited state and dropped-event
count. Expired `.ndjson` logs and `.pkl` checkpoints are pruned at server start.

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
# Python simulation and research regression suite (no API key/ClickHouse needed)
uv sync --frozen
uv run pytest -q

# Branch coverage for sim/; writes coverage.xml and enforces the 65% gate
uv run pytest -q --cov=sim --cov-report=term-missing --cov-report=xml

# Deterministic Agent Loop dataset gate (no LLM or Langfuse credentials)
PYTHONPATH=sim:research:. uv run python -m evaluation.agent_loop.cli \
  tests/fixtures/agent_loop_eval.jsonl --fail-on-hard

# Backend (vitest)
cd apps/server && npm test && npm run lint

# Frontend (build + lint; vitest for hooks/stores)
cd apps/web && npm run build && npm run lint && npx vitest run
```

### Continuous integration

The [GitHub Actions workflow](.github/workflows/ci.yml) runs on every pull
request and every push to `master`. Its Python 3.11 job installs the exact
`uv.lock` environment with a persistent uv cache, runs the hermetic pytest
suite, and enforces branch coverage for `sim/`. The initial baseline measured
on 2026-07-29 is **66%**, with a **65%** regression gate. Provider calls,
ClickHouse, web search, and generated datasets are mocked or skipped, so CI
does not require API keys or live network access.

Agent Loop and Multi-Agent evaluations are emitted as local `agent_scores` and
`run_scores` events and optionally mirrored to Langfuse. See
[`sim/evaluation/agent_loop/README.md`](sim/evaluation/agent_loop/README.md) for
the evaluator contracts, offline JSONL format, and explicit dataset sync.

The Server and Web jobs install the locked Node dependencies with `npm ci`,
cache npm downloads, and run server lint/tests/build plus web lint/build on
Node.js 20. The three jobs run independently so failures are easy to identify.
A path-filtered
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
| `/experiments/:id/replay?cursor=0&limit=1000` | GET | Bounded event-history page; follow `next_cursor` until `null` |
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
