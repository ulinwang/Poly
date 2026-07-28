# PolyMetl TypeScript Backend

Fastify-based rewrite of the Python FastAPI backend.

## Structure

```
backend/
├── src/
│   ├── index.ts          # Entry point
│   ├── server.ts         # Fastify instance setup
│   ├── config.ts         # Environment config
│   ├── db/
│   │   ├── index.ts      # better-sqlite3 connection + schema init
│   │   ├── experiments.ts # Experiment CRUD
│   │   └── settings.ts   # Settings CRUD
│   ├── routes/
│   │   ├── markets.ts    # Polymarket Gamma API proxy
│   │   ├── experiments.ts # Experiment create/cancel/read + SSE
│   │   ├── settings.ts   # API settings CRUD
│   │   └── providers.ts  # List available LLM providers
│   ├── services/
│   │   ├── polymarket.ts # Gamma API client with caching
│   │   └── runner.ts     # Experiment runner (mock)
│   ├── types/
│   │   └── index.ts      # Shared TypeScript types
│   └── tests/
│       ├── markets.test.ts
│       ├── experiments.test.ts
│       └── settings.test.ts
```

## Run

```bash
npm install
npm run dev        # development with tsx watch
npm run build      # compile to dist/
POLY_API_TOKEN="$(openssl rand -hex 32)" npm start
npm test           # vitest
```

Production mode requires a `POLY_API_TOKEN` of at least 32 characters. Send it
as `Authorization: Bearer <token>`. `POLY_API_READ_TOKEN` optionally grants
read-only access to protected routes; mutation attempts return HTTP 403.
Development mode is unauthenticated by default; set `POLY_API_TOKEN` to opt in.

Experiment requests are capped at 100 agents, 200 ticks, and 2 concurrently
active runs by default. Override these server-authoritative limits with
`POLY_MAX_EXPERIMENT_AGENTS`, `POLY_MAX_EXPERIMENT_TICKS`, and
`POLY_MAX_ACTIVE_RUNS`. The effective values are exposed by
`GET /api/v1/experiments/limits` for the web UI.

Production logging is structured JSON at `POLY_LOG_LEVEL` (`info` by default).
Fastify generates a UUID request ID, returns it as `X-Request-ID`, and redacts
authorization headers, cookies, API keys, and tokens. Runner lifecycle logs
contain run IDs and exit metadata, never provider stderr, prompts, or keys.

## API

- `GET /api/v1/health/live` (public liveness probe)
- `GET /api/v1/health/ready` (public SQLite/data-volume readiness probe)
- `GET /api/v1/markets?q=&limit=&live_only=`
- `GET /api/v1/markets/categories`
- `GET /api/v1/markets/:slug`
- `GET /api/v1/experiments?status=&slug=&limit=&offset=`
- `GET /api/v1/experiments/search?q=&limit=`
- `GET /api/v1/experiments/stats`
- `GET /api/v1/experiments/limits`
- `GET /api/v1/experiments/:id`
- `POST /api/v1/experiments`
- `POST /api/v1/experiments/:id/cancel`
- `GET /api/v1/experiments/:id/replay?cursor=0&limit=1000` (bounded page)
- `GET /api/v1/experiments/:id/events` (SSE)
- `GET /api/v1/settings/api`
- `PUT /api/v1/settings/api`
- `GET /api/v1/settings/general`
- `PUT /api/v1/settings/general`
- `GET /api/v1/providers`
