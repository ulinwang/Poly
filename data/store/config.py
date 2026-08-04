from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Polygon JSON-RPC endpoint
    RPC_URL: str

    # ClickHouse connection
    CLICKHOUSE_HOST: str = "localhost"
    CLICKHOUSE_PORT: int = 9000
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""
    CLICKHOUSE_DATABASE: str = "polymetl"

    # From/to blocks (inclusive). If unset, we will start from progress or latest - 10_000.
    START_BLOCK: int | None = None
    END_BLOCK: int | None = None

    # Batch sizes
    LOG_BATCH_SIZE: int = 2_000
    INSERT_BATCH_SIZE: int = 5_000

    # Contract address filter (optional). If provided, we filter logs by this address.
    EXCHANGE_ADDRESS: str | None = None

    # Network chain id (137 for Polygon mainnet)
    CHAIN_ID: int = 137

    # LLM provider settings (DeepSeek & Kimi are OpenAI-compatible)
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_TIMEOUT: float = 60.0
    DEEPSEEK_TEMPERATURE: float = 1.0

    KIMI_BASE_URL: str = "https://api.moonshot.cn/v1"
    KIMI_MODEL: str = "moonshot-v1-8k"
    KIMI_API_KEY: str | None = None
    KIMI_TIMEOUT: float = 60.0
    KIMI_TEMPERATURE: float = 1.0

    # Optional Langfuse observability. Disabled by default so a normal
    # simulation never imports the SDK or performs telemetry network I/O.
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    LANGFUSE_ENVIRONMENT: str = "development"
    LANGFUSE_RELEASE: str | None = None
    LANGFUSE_SAMPLE_RATE: float = Field(default=1.0, ge=0.0, le=1.0)
    # metadata: identifiers, status, model and token usage only.
    # full: also capture visible prompt/tool input and model output after
    # sensitive-key redaction. Hidden reasoning is never emitted upstream.
    LANGFUSE_CAPTURE_POLICY: Literal["metadata", "full"] = "metadata"
    LANGFUSE_FLUSH_TIMEOUT_SECONDS: float = Field(default=5.0, ge=0.0, le=60.0)

    @field_validator("LANGFUSE_ENVIRONMENT")
    @classmethod
    def validate_langfuse_environment(cls, value: str) -> str:
        if (
            not re.fullmatch(r"[a-z0-9_-]+", value)
            or value.startswith("langfuse")
        ):
            raise ValueError(
                "LANGFUSE_ENVIRONMENT must use lowercase letters, numbers, "
                "hyphens or underscores and must not start with 'langfuse'"
            )
        return value

    # v4 calibrated-init parameters (see docs/EXPERIMENT_LOG.md). The
    # signal sigma is the noise around the pre-event consensus mu the
    # agent receives at sim start. Higher empirical past accuracy →
    # tighter sigma. SCALE controls how aggressively past_accuracy
    # tightens the prior; FLOOR / CAP clip the result.
    SIGMA_SCALE: float = 0.4
    SIGMA_FLOOR: float = 0.05
    SIGMA_CAP: float = 0.4
    # Capital scaling for calibrated agents. FLOOR keeps tiny wallets
    # from being effectively zero; CAP prevents one whale from
    # dominating an N=20 simulation.
    CAPITAL_FLOOR_USD: float = 50.0
    CAPITAL_CAP_USD: float = 50_000.0
    # Pre-event consensus computation horizon (hours after market open).
    PRE_EVENT_VWAP_HOURS: float = 24.0

    model_config = SettingsConfigDict(env_file=(".env",), env_prefix="POLYMETL_", extra="ignore")


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
