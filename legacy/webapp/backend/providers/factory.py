"""Factory for creating LLM providers."""
from __future__ import annotations

from .base import LLMProvider
from .deepseek import DeepSeekProvider
from .openai import OpenAIProvider


PROVIDERS: dict[str, type[LLMProvider]] = {
    "deepseek": DeepSeekProvider,
    "openai": OpenAIProvider,
}


def get_provider(provider_id: str, api_key: str, model: str, **kwargs) -> LLMProvider:
    """Create a provider instance by ID."""
    cls = PROVIDERS.get(provider_id)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_id}. Available: {list(PROVIDERS.keys())}")
    return cls(api_key=api_key, model=model, **kwargs)


def list_providers() -> list[dict]:
    """List all available providers with metadata."""
    return [
        {
            "id": pid,
            "name": cls.display_name(),
            "models": cls.AVAILABLE_MODELS if hasattr(cls, "AVAILABLE_MODELS") else [],
            "requires_base_url": pid == "custom",
        }
        for pid, cls in PROVIDERS.items()
    ]
