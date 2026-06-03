"""Experiments API router."""
from __future__ import annotations

import time
import uuid
from fastapi import APIRouter, HTTPException

from database import get_experiments, get_experiment, save_experiment
from models.experiment import (
    ExperimentConfig, CreateExperimentResponse,
    CancelExperimentResponse, Experiment,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])

# In-memory experiment state (mirrored from old server.py)
_RUNS: dict[str, dict] = {}


@router.get("")
def list_experiments(limit: int = 100):
    exps = get_experiments(limit)
    return {"experiments": exps}


@router.get("/{exp_id}")
def read_experiment(exp_id: str):
    exp = get_experiment(exp_id)
    if exp is None:
        raise HTTPException(404, "Experiment not found")
    return {"experiment": exp}


@router.post("", response_model=CreateExperimentResponse)
def create_experiment(config: ExperimentConfig):
    run_id = uuid.uuid4().hex[:12]
    now = time.time()
    exp = {
        "id": run_id,
        "slug": config.slug,
        "n_agents": config.n_agents,
        "n_ticks": config.n_ticks,
        "persona_set": config.persona_set,
        "status": "running",
        "started_at": now,
        "finished_at": None,
        "elapsed_s": 0,
        "result_summary": None,
    }
    save_experiment(exp)
    _RUNS[run_id] = {
        **exp,
        "cancelled": False,
    }
    return {"run_id": run_id}


@router.post("/{exp_id}/cancel", response_model=CancelExperimentResponse)
def cancel_experiment(exp_id: str):
    run = _RUNS.get(exp_id)
    if run is None:
        raise HTTPException(404, "Experiment not found")
    run["cancelled"] = True
    run["status"] = "cancelled"
    run["finished_at"] = time.time()
    save_experiment(run)
    return {"cancelled": True}


@router.get("/{exp_id}/events")
async def stream_experiment_events(exp_id: str, replay: int = 1):
    # Placeholder: SSE streaming will be implemented in Phase 4
    # For now, return a mock stream endpoint
    from fastapi.responses import StreamingResponse
    import asyncio

    async def generator():
        yield b"event: ping\ndata: {}\n\n"
        await asyncio.sleep(1)
        yield b"event: done\ndata: {}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")
