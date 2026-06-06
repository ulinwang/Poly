# Deprecated Python Backend

⚠️ **This directory (`webapp/backend/`) is deprecated and kept for reference only.**

## Active Backend

The current backend is written in **TypeScript** using **Fastify** and lives in the top-level `backend/` directory:

```bash
cd backend
npm install
npm run dev    # dev mode with hot reload on :8765
npm run build  # compile to dist/
npm start      # production mode
```

## Why the Switch?

- **Type safety** across the entire API surface
- **Unified build pipeline** — frontend and backend share tooling (Vite, Vitest)
- **Better SPA static-file serving** with built-in fallback to `index.html`
- **Faster cold-start** for development

## What's Still Here

| File | Purpose |
|------|---------|
| `server_v2.py` | Legacy FastAPI entry point |
| `database.py` | Legacy SQLite persistence |
| `routers/` | Legacy route modules (settings, markets, experiments) |
| `models/` | Legacy Pydantic request/response models |
| `providers/` | Legacy LLM provider abstractions (DeepSeek, OpenAI) |

These modules are **not imported by the active TS backend**. The TS backend calls the Python simulation core (`webapp/runner_stream.py`) directly via a CLI wrapper (`webapp/runner_cli.py`) spawned as a child process.

## Removal Timeline

This directory will be removed in a future release once the TS backend has been battle-tested in production.
