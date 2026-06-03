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


class ModelShare(BaseModel):
    """One LLM model and its share, for the model-heterogeneity
    experiment. RESERVED scaffold — not yet active; pending
    multi-model API access."""
    model: str
    weight: float = Field(..., gt=0)


class AgentConfig(BaseModel):
    # `model_mix` starts with the pydantic-protected `model_` prefix;
    # disable the namespace guard since it is an intended field name.
    model_config = {"protected_namespaces": ()}

    population: Literal[
        "calibrated", "hand_coded", "archetype", "no_signal",
        "marginal_random", "uniform_random",
    ] = "calibrated"
    features: list[str] = Field(default_factory=lambda: ["wallet", "market", "temporal"])
    persona_recipe: PersonaRecipe = Field(default_factory=PersonaRecipe)
    n_agents: Optional[int] = None        # None = all wallets with cached profile
    seed: int = 0
    # v13 (audit L-6): which signal does derive_priors expose as the
    # private-information anchor for agents?
    #   - first_window_vwap : current default; 24h post-open VWAP
    #   - bootstrap_anchor  : reuse the orderbook bootstrap anchor_yes
    signal_mu_source: Literal["first_window_vwap", "bootstrap_anchor"] = "first_window_vwap"
    # v13 (B4): toggle the AGT-4 update_belief tool. Default True keeps
    # the post-merge behaviour (tool always offered to the LLM); set False
    # in B4 ablation configs to fall back to v12 tool inventory.
    belief_update_enabled: bool = True
    # Override the mix of market-user behaviour profiles for the
    # archetype population. None = use the empirical cluster proportions.
    # When set, the list length must equal the number of clusters K;
    # values are non-negative weights (need not sum to 1).
    archetype_weights: Optional[list[float]] = None
    # RESERVED scaffold for the model-heterogeneity experiment: when set,
    # agents are assigned LLM models by these weights instead of all
    # using a single llm.model. None = homogeneous (every agent uses
    # llm.model). NOT YET ACTIVE — the runner does not consume this field
    # until multi-model API access is available; configs may declare it
    # so the experiment design is reserved.
    model_mix: Optional[list[ModelShare]] = None


class EnvironmentConfig(BaseModel):
    observer: Literal["quote_only", "tape", "full_book"] = "quote_only"
    seeder: Literal["from_clob_history", "from_holders", "none"] = "from_clob_history"
    fees_override_bps: Optional[float] = None       # None → use clob_markets.taker_base_fee


class LLMRetry(BaseModel):
    max_attempts: int = 3
    backoff_base_s: float = 2.0


class LLMConfig(BaseModel):
    model: Optional[str] = None         # None → Settings.DEEPSEEK_MODEL
    temperature: float = 1.0
    timeout_s: float = 120.0
    retry: LLMRetry = Field(default_factory=LLMRetry)
    prompt_language: Literal["en", "zh"] = "en"
    # DeepSeek hybrid reasoning toggle. None = API default (thinking on);
    # True/False force the thinking mode for the thinking-vs-nonthinking
    # experiment.
    thinking: Optional[bool] = None
    # v9.3: parallel per-tick LLM calls. 0 or 1 = serial (legacy
    # behavior); None = auto (= n_agents capped at 16, polite default).
    concurrency: Optional[int] = None


class OutputConfig(BaseModel):
    dual_write_clickhouse: bool = True
    parquet_compression: Literal["zstd", "snappy", "gzip", "uncompressed"] = "zstd"
    output_dir: str = "output"


class ExperimentBlock(BaseModel):
    """Optional v13 wrapper for experiment-level toggles."""
    # Override the empirically derived simulation horizon (priors["n_ticks"]).
    # Used by the tick-horizon experiment to hold every other parameter
    # fixed while sweeping only the number of decision rounds.
    n_ticks_override: Optional[int] = Field(default=None, ge=1)
    # Long-tick runs can emit compact checkpoint artifacts for context
    # handoff. Disabled by default so existing experiment outputs do not
    # change unless a config opts in.
    checkpoint_enabled: bool = False
    checkpoint_interval_ticks: int = Field(default=5, ge=1)
    checkpoint_compact_char_budget: Optional[int] = Field(default=None, ge=1)
    checkpoint_recent_ticks: int = Field(default=5, ge=1)


class ExperimentConfig(BaseModel):
    name: str = "baseline"
    description: str = ""
    market: MarketConfig
    agent: AgentConfig = Field(default_factory=AgentConfig)
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    # v13: optional experiment-level extension hooks.
    experiment: ExperimentBlock = Field(default_factory=ExperimentBlock)


def parse_config(data: dict) -> ExperimentConfig:
    """dict → ExperimentConfig with defaults applied."""
    return ExperimentConfig.model_validate(data)
