"""Experiments API router."""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from database import (
    get_experiments, get_experiment, save_experiment,
    get_experiments_filtered, search_experiments as search_experiments_db,
    get_experiment_stats,
)
from models.experiment import (
    ExperimentConfig, CreateExperimentResponse,
    CancelExperimentResponse,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])

# -------------------------------------------------------------------
# Run registry — keeps a per-run event queue + cancellation flag
# -------------------------------------------------------------------

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
    final_metrics: dict = field(default_factory=dict)
    tick_elapsed_s_total: float = 0.0
    tick_count: int = 0

_RUNS: dict[str, RunHandle] = {}
_RUNS_LOCK = threading.Lock()
_HISTORY_CAP = 2000


def _make_emitter(handle: RunHandle):
    def emit(kind: str, data: dict) -> None:
        handle.queue.put((kind, data))
        if len(handle.history) < _HISTORY_CAP:
            handle.history.append((kind, data))
        if kind == "settled":
            handle.final_metrics = data
        elif kind == "tick_finished":
            handle.tick_elapsed_s_total += data.get("elapsed_s", 0)
            handle.tick_count += 1
    return emit


def _spawn_run(handle: RunHandle) -> None:
    emit = _make_emitter(handle)

    def _worker():
        crashed = False
        try:
            # Import runner here to avoid startup cost
            from webapp.runner_stream import run_stream
            run_stream(
                slug=handle.slug,
                n_agents=handle.n_agents,
                n_ticks_override=handle.n_ticks,
                persona_set=handle.persona_set,
                on_event=emit,
                cancel=handle.cancel,
            )
        except Exception as exc:
            crashed = True
            logging = __import__("logging")
            logging.getLogger(__name__).exception("run %s crashed", handle.run_id)
            emit("error", {"where": "worker", "message": str(exc)})
        finally:
            handle.finished = True
            emit("__end__", {})
            metrics = handle.final_metrics
            payload: dict = {
                "id": handle.run_id,
                "finished_at": time.time(),
                "result_summary": json.dumps(metrics) if metrics else None,
                "final_yes_mid": metrics.get("yes_mid_final"),
                "total_fills": metrics.get("n_fills"),
                "total_actions": metrics.get("n_actions"),
                "avg_tick_time_ms": round(
                    handle.tick_elapsed_s_total / handle.tick_count * 1000, 2
                ) if handle.tick_count else None,
            }
            if crashed:
                payload["status"] = "error"
            elif not handle.cancel.is_set():
                payload["status"] = "completed"
            save_experiment(payload)

    threading.Thread(target=_worker, name=f"run-{handle.run_id[:8]}",
                     daemon=True).start()


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------

@router.get("")
def list_experiments(
    status: str | None = None,
    slug: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    exps, total = get_experiments_filtered(status=status, slug=slug, limit=limit, offset=offset)
    return {"experiments": exps, "total": total, "limit": limit, "offset": offset}


@router.get("/search")
def search_experiments(q: str = "", limit: int = 20):
    if not q:
        return {"experiments": []}
    exps = search_experiments_db(q=q, limit=limit)
    return {"experiments": exps}


@router.get("/stats")
def experiments_stats():
    return get_experiment_stats()


@router.get("/{exp_id}")
def read_experiment(exp_id: str):
    exp = get_experiment(exp_id)
    if exp is None:
        # Fallback to in-memory
        handle = _RUNS.get(exp_id)
        if handle:
            exp = {
                "id": handle.run_id,
                "slug": handle.slug,
                "n_agents": handle.n_agents,
                "n_ticks": handle.n_ticks,
                "persona_set": handle.persona_set,
                "status": "running" if not handle.finished else "completed",
                "started_at": handle.started_at,
                "finished_at": time.time() if handle.finished else None,
                "elapsed_s": round(time.time() - handle.started_at, 1),
                "result_summary": None,
            }
        else:
            raise HTTPException(404, "Experiment not found")
    return {"experiment": exp}


@router.post("", response_model=CreateExperimentResponse)
def create_experiment(config: ExperimentConfig):
    run_id = uuid.uuid4().hex[:12]
    handle = RunHandle(
        run_id=run_id, slug=config.slug,
        n_agents=config.n_agents, n_ticks=config.n_ticks,
        persona_set=config.persona_set,
    )
    with _RUNS_LOCK:
        _RUNS[run_id] = handle

    # Persist to SQLite
    save_experiment({
        "id": run_id,
        "slug": config.slug,
        "n_agents": config.n_agents,
        "n_ticks": config.n_ticks,
        "persona_set": config.persona_set,
        "status": "running",
        "started_at": time.time(),
        "finished_at": None,
        "elapsed_s": 0,
        "result_summary": None,
    })

    _spawn_run(handle)
    return {"run_id": run_id}


@router.post("/{exp_id}/cancel", response_model=CancelExperimentResponse)
def cancel_experiment(exp_id: str):
    handle = _RUNS.get(exp_id)
    if handle is None:
        raise HTTPException(404, "Experiment not found")
    handle.cancel.set()
    save_experiment({
        "id": exp_id,
        "status": "cancelled",
        "finished_at": time.time(),
    })
    return {"cancelled": True}


@router.get("/{exp_id}/events")
async def stream_events(exp_id: str, request: Request, replay: int = 1):
    handle = _RUNS.get(exp_id)
    if handle is None:
        raise HTTPException(404, "Experiment not found")

    async def generator():
        # Replay buffered history first
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
