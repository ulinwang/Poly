"""Pydantic models for settings endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr


class ApiSettings(BaseModel):
    id: int | None = None
    provider: str = Field(default="deepseek", pattern=r"^(deepseek|openai|anthropic|custom)$")
    model: str = Field(default="deepseek-chat", min_length=1)
    api_key: str = Field(default="", min_length=1)
    base_url: str | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=256, le=8192)


class ApiSettingsResponse(BaseModel):
    settings: ApiSettings


class ProviderInfo(BaseModel):
    id: str
    name: str
    models: list[str]
    requires_base_url: bool


class ProvidersResponse(BaseModel):
    providers: list[ProviderInfo]
