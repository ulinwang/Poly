"""DeepSeek chat-completions client (OpenAI-compatible).

Two entry points:

  call_deepseek(...)             — text-mode completion. Used by the
                                    persona generator (agent.personas.calibrated)
                                    where we want a free-form paragraph.

  call_deepseek_with_tools(...)  — function-tool mode. Used by the
                                    per-tick trader decision flow
                                    (agent.decision.runtime). The caller
                                    may let the LLM choose a tool or force
                                    a specific tool for staged decisions.

Stateless, synchronous. The OpenAI Python SDK is the underlying
transport — DeepSeek exposes an OpenAI-compatible endpoint.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Optional

from openai import OpenAI


@lru_cache(maxsize=4)
def _client(api_key: str, base_url: str, timeout: float) -> OpenAI:
    """Process-singleton OpenAI client per (api_key, base_url, timeout).

    The OpenAI SDK is thread-safe and pools HTTP connections internally,
    so a single client serves all concurrent agent decisions. The cache
    is keyed because tests inject distinct api_key/base_url stubs.
    """
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
    tool_choice: str | dict = "auto",
    thinking: Optional[bool] = None,
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
    # `thinking` toggles the DeepSeek hybrid reasoning mode. None keeps
    # the API default (thinking on); True/False force enabled/disabled.
    extra_body: dict[str, Any] = {}
    if thinking is not None:
        extra_body["thinking"] = {
            "type": "enabled" if thinking else "disabled"
        }
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        tools=tools,
        tool_choice=tool_choice,
        extra_body=extra_body or None,
    )
    msg = resp.choices[0].message
    usage = resp.usage

    # v13 (AGT-4): expose ALL tool calls (not just the first). The
    # `update_belief` tool can be paired with a trade tool in the same
    # response — the runtime composes them. `tool_call` continues to
    # point at the first non-`update_belief` call (or the first call if
    # all are belief updates) so legacy callers keep working.
    tool_calls_payload: list[dict] = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls_payload.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": args,
            })

    tool_call_payload = None
    if tool_calls_payload:
        # Prefer a non-belief call as the "primary" (trade) action.
        non_belief = [t for t in tool_calls_payload
                      if t.get("name") != "update_belief"]
        tool_call_payload = (non_belief or tool_calls_payload)[0]

    return {
        "tool_call": tool_call_payload,
        "tool_calls": tool_calls_payload,
        "text": msg.content or "",
        "prompt_tokens": int(usage.prompt_tokens) if usage else 0,
        "completion_tokens": int(usage.completion_tokens) if usage else 0,
        "raw": resp.model_dump_json(),
    }
