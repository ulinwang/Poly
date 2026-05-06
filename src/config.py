from __future__ import annotations

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

    # DeepSeek agent simulation (src/agent.py)
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_TIMEOUT: float = 60.0
    DEEPSEEK_TEMPERATURE: float = 0.0

    model_config = SettingsConfigDict(env_file=(".env",), env_prefix="POLYMETL_", extra="ignore")


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
