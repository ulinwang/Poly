"""Base class for LLM providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMProvider(ABC):
    """Abstract base for LLM API providers."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None, **kwargs):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.extra = kwargs

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        """Send a chat completion request and return the response text."""
        ...

    @abstractmethod
    async def stream_chat(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        """Stream a chat completion response."""
        ...

    @property
    @abstractmethod
    def models(self) -> list[str]:
        """List of available models for this provider."""
        ...

    @classmethod
    @abstractmethod
    def display_name(cls) -> str:
        """Human-readable provider name."""
        ...
