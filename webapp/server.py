"""FastAPI app exposing the streaming runner to the Vue 3 frontend.

Endpoints:
  GET  /              -> static/index.html
  GET  /api/markets   -> recent open markets (with optional ?q=...)
  POST /api/runs      -> body {slug, n_agents, n_ticks, persona_set}
                         returns {run_id}; spawns a daemon thread
  GET  /api/runs/{rid}/events  -> Server-Sent Events stream
  POST /api/runs/{rid}/cancel  -> cancel a running sim

Run:
    uv run python -m webapp.server
or
    uvicorn webapp.server:app --host 0.0.0.0 --port 8765 --reload
"""
from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from data.query._ch import get_ch
from webapp.runner_stream import run_stream


log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
STATIC = ROOT / "static"


# --------------------------------------------------------------------
# Run registry — keeps a per-run event queue + cancellation flag
# --------------------------------------------------------------------


@dataclass
class RunHandle:
    run_id: str
    slug: str
    n_agents: int
    n_ticks: int
    persona_set: str
    queue: "queue.Queue[tuple[str, dict]]" = field(default_factory=queue.Queue)
    cancel: threading.Event = field(default_factory=threading.Event)
    started_at: float = field(default_factory=time.time)
    finished: bool = False
    history: list[tuple[str, dict]] = field(default_factory=list)


_RUNS: dict[str, RunHandle] = {}
_RUNS_LOCK = threading.Lock()
_HISTORY_CAP = 2000


def _make_emitter(handle: RunHandle):
    def emit(kind: str, data: dict) -> None:
        handle.queue.put((kind, data))
        if len(handle.history) < _HISTORY_CAP:
            handle.history.append((kind, data))
    return emit


def _spawn_run(handle: RunHandle) -> None:
    emit = _make_emitter(handle)

    def _worker():
        try:
            run_stream(
                slug=handle.slug,
                n_agents=handle.n_agents,
                n_ticks_override=handle.n_ticks,
                persona_set=handle.persona_set,
                on_event=emit,
                cancel=handle.cancel,
            )
        except Exception as exc:        # noqa: BLE001
            log.exception("run %s crashed", handle.run_id)
            emit("error", {"where": "worker", "message": str(exc)})
        finally:
            handle.finished = True
            emit("__end__", {})        # sentinel for SSE generator

    threading.Thread(target=_worker, name=f"run-{handle.run_id[:8]}",
                     daemon=True).start()


# --------------------------------------------------------------------
# FastAPI app
# --------------------------------------------------------------------


app = FastAPI(title="PolyMetl Live Demo", version="0.1.0")

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


from webapp.explorer import router as explorer_router

app.include_router(explorer_router)


@app.get("/")
def index():
    p = STATIC / "index.html"
    if not p.exists():
        return JSONResponse({"error": "index.html not yet built"}, status_code=500)
    return FileResponse(str(p))


@app.get("/explore")
def explore_page():
    p = STATIC / "explore.html"
    if not p.exists():
        return JSONResponse({"error": "explore.html not yet built"}, status_code=500)
    return FileResponse(str(p))


# ----- markets -----


class MarketRow(BaseModel):
    slug: str
    question: str
    condition_id: str
    volume: float
    is_live: bool
    end_date_iso: str | None = None
    n_holders: int | None = None


@app.get("/api/markets")
def list_markets(q: str = "", limit: int = 30, live_only: bool = False):
    """Search clob_markets / markets_full. Open (live) markets first."""
    ch = get_ch(None)
    pattern = f"%{q.lower()}%" if q else "%"
    rows = ch.client.execute(
        """
        SELECT cm.market_slug, cm.question, cm.condition_id,
               coalesce(mf.volume_num, 0.0) AS volume,
               mr.winning_idx,
               toString(mf.end_date) AS end_iso
        FROM polymetl.clob_markets cm
        LEFT JOIN polymetl.markets_full mf USING (condition_id)
        LEFT JOIN polymetl.markets_resolved mr USING (condition_id)
        WHERE lower(cm.market_slug) LIKE %(pat)s
           OR lower(cm.question) LIKE %(pat)s
        ORDER BY (mr.winning_idx IS NULL) DESC,
                 volume DESC
        LIMIT %(lim)s
        """,
        {"pat": pattern, "lim": int(limit)},
    )
    out = []
    for slug, question, cid, vol, winning_idx, end_iso in rows:
        is_live = winning_idx is None or winning_idx < 0
        if live_only and not is_live:
            continue
        out.append(MarketRow(
            slug=slug, question=question or "", condition_id=cid,
            volume=float(vol or 0.0), is_live=bool(is_live),
            end_date_iso=end_iso or None,
        ).model_dump())
    return {"markets": out}


# ----- run lifecycle -----


class RunRequest(BaseModel):
    slug: str
    n_agents: int = Field(default=20, ge=2, le=200)
    n_ticks: int = Field(default=12, ge=1, le=120)
    persona_set: str = Field(default="archetype")


@app.post("/api/runs")
def start_run(req: RunRequest):
    if req.persona_set not in ("archetype", "calibrated", "no_signal"):
        raise HTTPException(400, f"unknown persona_set {req.persona_set!r}")
    run_id = uuid.uuid4().hex[:12]
    handle = RunHandle(
        run_id=run_id, slug=req.slug,
        n_agents=req.n_agents, n_ticks=req.n_ticks,
        persona_set=req.persona_set,
    )
    with _RUNS_LOCK:
        _RUNS[run_id] = handle
    _spawn_run(handle)
    return {"run_id": run_id}


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    handle = _RUNS.get(run_id)
    if handle is None:
        raise HTTPException(404, "run not found")
    handle.cancel.set()
    return {"cancelled": True}


@app.get("/api/runs/{run_id}")
def run_status(run_id: str):
    handle = _RUNS.get(run_id)
    if handle is None:
        raise HTTPException(404, "run not found")
    return {
        "run_id": handle.run_id, "slug": handle.slug,
        "n_agents": handle.n_agents, "n_ticks": handle.n_ticks,
        "persona_set": handle.persona_set, "finished": handle.finished,
        "elapsed_s": round(time.time() - handle.started_at, 1),
    }


@app.get("/api/runs/{run_id}/events")
async def stream_events(run_id: str, request: Request, replay: int = 1):
    handle = _RUNS.get(run_id)
    if handle is None:
        raise HTTPException(404, "run not found")

    async def generator():
        # Replay buffered history first so a late-joining client
        # doesn't lose the agent roster / market metadata events.
        if replay:
            for kind, data in list(handle.history):
                if kind == "__end__":
                    continue
                yield {"event": kind, "data": json.dumps(data, default=str)}
        loop = asyncio.get_event_loop()
        while True:
            if await request.is_disconnected():
                break
            try:
                kind, data = await loop.run_in_executor(
                    None, lambda: handle.queue.get(timeout=15.0),
                )
            except queue.Empty:
                yield {"event": "ping", "data": "{}"}
                if handle.finished:
                    break
                continue
            if kind == "__end__":
                yield {"event": "end", "data": "{}"}
                break
            yield {"event": kind, "data": json.dumps(data, default=str)}

    return EventSourceResponse(generator())


def main() -> None:
    import argparse
    import uvicorn

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
        "webapp.server:app", host=args.host, port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
