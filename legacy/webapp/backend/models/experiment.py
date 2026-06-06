"""Pydantic models for experiment endpoints."""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ExperimentConfig(BaseModel):
    slug: str = Field(min_length=1)
    n_agents: int = Field(default=20, ge=2, le=200)
    n_ticks: int = Field(default=12, ge=1, le=120)
    persona_set: str = Field(default="archetype", pattern=r"^(archetype|calibrated|no_signal)$")
    api_settings_id: int | None = None


class Experiment(BaseModel):
    id: str
    slug: str
    n_agents: int
    n_ticks: int
    persona_set: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_s: float = 0.0
    result_summary: dict | None = None


class CreateExperimentResponse(BaseModel):
    run_id: str


class CancelExperimentResponse(BaseModel):
    cancelled: bool
