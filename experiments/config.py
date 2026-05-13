"""Experiment configuration schema (pydantic).

Loaded from YAML by `experiments.runner.load_config`. Defaults
preserve v7 behavior so an empty config gives the v7 reference run
on whatever slug the user passes.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class MarketConfig(BaseModel):
    slug: str
    # v8 only supports market_open; v9 adds asof support.
    asof: Literal["market_open"] = "market_open"


class PersonaRecipe(BaseModel):
    use_bio: bool = True
    sanitize_labels: bool = True
    llm_temperature: float = 0.0
    cache_path: str = "data/wallet_personas.json"


class AgentConfig(BaseModel):
    population: Literal[
        "calibrated", "hand_coded", "archetype", "no_signal",
        "marginal_random", "uniform_random",
    ] = "calibrated"
    features: list[str] = Field(default_factory=lambda: ["wallet", "market", "temporal"])
    persona_recipe: PersonaRecipe = Field(default_factory=PersonaRecipe)
    n_agents: Optional[int] = None        # None = all wallets with cached profile
    seed: int = 0
    # v13 (B4): forward-compatible flag for the belief-update tool
    # that AGT-4 is wiring. The runner will dispatch on this once the
    # tool exists; configs already commit to a value so B4 runs can
    # fire the day AGT-4 merges.
    belief_update_enabled: bool = False


class EnvironmentConfig(BaseModel):
    observer: Literal["quote_only", "tape", "full_book"] = "quote_only"
    seeder: Literal["from_clob_history", "from_holders", "none"] = "from_clob_history"
    fees_override_bps: Optional[float] = None       # None → use clob_markets.taker_base_fee


class LLMRetry(BaseModel):
    max_attempts: int = 3
    backoff_base_s: float = 2.0


class LLMConfig(BaseModel):
    model: Optional[str] = None         # None → Settings.DEEPSEEK_MODEL
    temperature: float = 0.0
    timeout_s: float = 120.0
    retry: LLMRetry = Field(default_factory=LLMRetry)
    # v9.3: parallel per-tick LLM calls. 0 or 1 = serial (legacy
    # behavior); None = auto (= n_agents capped at 16, polite default).
    concurrency: Optional[int] = None


class OutputConfig(BaseModel):
    dual_write_clickhouse: bool = True
    parquet_compression: Literal["zstd", "snappy", "gzip", "uncompressed"] = "zstd"
    output_dir: str = "output"


class ShockPayload(BaseModel):
    text: str


class ShockConfig(BaseModel):
    """v13 (B6) — synthetic news shock injected mid-run.

    When set, the runner appends a synthetic memory entry of shape
    ``{tick, action: 'EXTERNAL_NEWS', reasoning: payload.text}``
    to every agent at tick ``tick``, so the NEXT tick's prompt's
    "recent_decisions" block carries it."""
    tick: int = Field(..., ge=0)
    kind: Literal["rumor"] = "rumor"
    payload: ShockPayload


class ExperimentBlock(BaseModel):
    """Optional v13 wrapper for experiment-level toggles."""
    shock: Optional[ShockConfig] = None


class ExperimentConfig(BaseModel):
    name: str = "baseline"
    description: str = ""
    market: MarketConfig
    agent: AgentConfig = Field(default_factory=AgentConfig)
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    # v13: optional experiment-level shock / extension hooks.
    experiment: ExperimentBlock = Field(default_factory=ExperimentBlock)


def parse_config(data: dict) -> ExperimentConfig:
    """dict → ExperimentConfig with defaults applied."""
    return ExperimentConfig.model_validate(data)
