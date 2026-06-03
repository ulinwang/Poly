"""FastAPI v2 backend — modular routers, SQLite persistence, LLM provider abstraction.

This is the new backend that serves the React frontend while maintaining
backward compatibility with the existing SSE streaming runner.

Run:
    uv run python -m webapp.backend.server_v2 --port 8765
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import uvicorn

from routers.settings import router as settings_router
from routers.markets import router as markets_router
from routers.experiments import router as experiments_router

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
FRONTEND_DIST = ROOT.parent / "frontend" / "dist"

app = FastAPI(title="PolyMetl v2", version="0.2.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(settings_router, prefix="/api/v1")
app.include_router(markets_router, prefix="/api/v1")
app.include_router(experiments_router, prefix="/api/v1")

# Fallback SPA routes — serve index.html for all non-API routes
@app.get("/{path:path}")
def spa_fallback(path: str):
    """Serve React SPA for all non-API routes."""
    # Skip API routes
    if path.startswith("api/"):
        from fastapi import HTTPException
        raise HTTPException(404, "API endpoint not found")

    index_html = FRONTEND_DIST / "index.html"
    if index_html.exists():
        return FileResponse(str(index_html))
    return {"message": "PolyMetl v2 API is running. Build the frontend first."}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(
        "webapp.backend.server_v2:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
