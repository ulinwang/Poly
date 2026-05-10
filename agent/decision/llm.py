"""DeepSeek chat-completions client (OpenAI-compatible).

Two entry points:

  call_deepseek(...)             — text-mode completion. Used by the
                                    persona generator (agent.personas.calibrated)
                                    where we want a free-form paragraph.

  call_deepseek_with_tools(...)  — function-tool mode. Used by the
                                    per-tick trader decision flow
                                    (agent.decision.runtime). The LLM
                                    chooses which of `tools` to call;
                                    response is a tool_calls[0] object,
                                    or text if it declines (= HOLD).

Stateless, synchronous. The OpenAI Python SDK is the underlying
transport — DeepSeek exposes an OpenAI-compatible endpoint.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from openai import OpenAI


def _client(api_key: str, base_url: str, timeout: float) -> OpenAI:
    """Build a per-call client. SDK pools its own HTTP connections."""
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)


def call_deepseek(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    timeout: float = 60.0,
    response_format: Optional[dict] = None,
) -> dict:
    """Send one chat-completion request, text mode.

    Returns: {"text", "prompt_tokens", "completion_tokens", "raw"}.

    `response_format={"type": "json_object"}` available for callers
    that need DeepSeek's strict-JSON mode (legacy persona path).
    """
    client = _client(api_key, base_url, timeout)
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    usage = resp.usage
    return {
        "text": msg.content or "",
        "prompt_tokens": int(usage.prompt_tokens) if usage else 0,
        "completion_tokens": int(usage.completion_tokens) if usage else 0,
        "raw": resp.model_dump_json(),
    }


def call_deepseek_with_tools(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    tools: list[dict],
    temperature: float = 0.0,
    timeout: float = 60.0,
    tool_choice: str = "auto",
) -> dict:
    """Send one chat-completion request with OpenAI function tools.

    Returns:
      {
        "tool_call": {                       # or None if LLM declined
            "id": "...",
            "name": "place_limit_order",
            "arguments": {"outcome": "YES", ...},
        },
        "text": str,                         # LLM prose (often empty when tool was called)
        "prompt_tokens": int,
        "completion_tokens": int,
        "raw": str,                          # full response JSON
      }
    """
    client = _client(api_key, base_url, timeout)
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        tools=tools,
        tool_choice=tool_choice,
    )
    msg = resp.choices[0].message
    usage = resp.usage

    tool_call_payload = None
    if msg.tool_calls:
        tc = msg.tool_calls[0]
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        tool_call_payload = {
            "id": tc.id,
            "name": tc.function.name,
            "arguments": args,
        }

    return {
        "tool_call": tool_call_payload,
        "text": msg.content or "",
        "prompt_tokens": int(usage.prompt_tokens) if usage else 0,
        "completion_tokens": int(usage.completion_tokens) if usage else 0,
        "raw": resp.model_dump_json(),
    }
