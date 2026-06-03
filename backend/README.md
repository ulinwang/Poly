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
npm start          # run compiled output
npm test           # vitest
```

## API

- `GET /api/v1/markets?q=&limit=&live_only=`
- `GET /api/v1/markets/categories`
- `GET /api/v1/markets/:slug`
- `GET /api/v1/experiments?status=&slug=&limit=&offset=`
- `GET /api/v1/experiments/search?q=&limit=`
- `GET /api/v1/experiments/stats`
- `GET /api/v1/experiments/:id`
- `POST /api/v1/experiments`
- `POST /api/v1/experiments/:id/cancel`
- `GET /api/v1/experiments/:id/events` (SSE)
- `GET /api/v1/settings/api`
- `PUT /api/v1/settings/api`
- `GET /api/v1/settings/general`
- `PUT /api/v1/settings/general`
- `GET /api/v1/providers`
