"""DeepSeek provider implementation."""
from __future__ import annotations

from typing import AsyncIterator

from .base import LLMProvider


class DeepSeekProvider(LLMProvider):
    """DeepSeek API provider (OpenAI-compatible)."""

    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
    AVAILABLE_MODELS = ["deepseek-chat", "deepseek-reasoner"]

    def __init__(self, api_key: str, model: str = "deepseek-chat", base_url: str | None = None, **kwargs):
        super().__init__(api_key, model, base_url or self.DEFAULT_BASE_URL, **kwargs)
        try:
            import openai
            self.client = openai.AsyncOpenAI(api_key=api_key, base_url=self.base_url)
        except ImportError:
            self.client = None

    async def chat(self, messages: list[dict], **kwargs) -> str:
        if self.client is None:
            raise RuntimeError("openai package not installed")
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=kwargs.get("temperature", self.extra.get("temperature", 0.7)),
            max_tokens=kwargs.get("max_tokens", self.extra.get("max_tokens", 2048)),
        )
        return resp.choices[0].message.content or ""

    async def stream_chat(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        if self.client is None:
            raise RuntimeError("openai package not installed")
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=kwargs.get("temperature", self.extra.get("temperature", 0.7)),
            max_tokens=kwargs.get("max_tokens", self.extra.get("max_tokens", 2048)),
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    @property
    def models(self) -> list[str]:
        return self.AVAILABLE_MODELS

    @classmethod
    def display_name(cls) -> str:
        return "DeepSeek"
