# Poly Web

Web UI for **Poly**, a multi-agent simulation of decentralized prediction
markets. It lets you browse live Polymarket events, inspect market detail,
launch simulation experiments (LLM-driven agents trading on a market), and
watch runs live — order flow, per-tick metrics, agent forum activity, and the
social follow graph.

## Tech stack

- React 19 + TypeScript + Vite
- Tailwind CSS v4
- zustand (state stores, lightweight localStorage persistence)
- react-router-dom (hash routing)
- recharts (charts), @tanstack/react-virtual (virtualized lists)
- vitest + @testing-library/react (unit tests), ESLint

## Commands

Run from this directory:

```bash
npm run dev       # start the Vite dev server
npm run build     # type-check (tsc -b) + production build
npm run test      # run unit tests (vitest run)
npm run lint      # ESLint
npm run preview   # preview the production build
```

This package is part of the npm workspaces monorepo rooted at the repository
root, which also exposes `npm run dev:web`, `build:web`, `test:web`, and
`lint:web` from the root.

## Layout

- `src/pages/` — top-level routes: `MarketBrowser`, `MarketDetail`,
  `ExperimentManager`, `ExperimentLive`, `AgentInfo`, `DataAnalysis`,
  `Settings`
- `src/components/` — shared UI (layout, error boundary, auth gate)
- `src/stores/` — zustand stores (market feed, experiment live state, settings)
- `src/hooks/` — shared hooks (SSE stream, replay player, debounce, formatting)
- `src/lib/` — API client, i18n, market filtering helpers
- `src/types/` — shared TypeScript types

The dev server proxies API calls to the backend (`apps/server`); see the root
README for running the full stack.
