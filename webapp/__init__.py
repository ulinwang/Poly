"""v12 — live web demo (FastAPI + SSE + Vue 3 dashboard).

Reuses the data/agent/environment stack via a streaming wrapper around
the YAML-driven runner. Adds:
  - on-the-fly priors derivation for live (non-closed) markets
  - per-tick / per-agent SSE event emission
  - a Vue 3 SPA mirroring the MiroFish multi-pane dashboard layout
"""
