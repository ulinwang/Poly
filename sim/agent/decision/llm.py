"""Unified LLM chat-completions client, backed by litellm.

Two entry points (names kept for backward compatibility — callers in
agent.decision.runtime and agent.personas.calibrated inject them as
`call_fn`):

  call_deepseek(...)             — text-mode completion. Used by the
                                    persona generator (agent.personas.calibrated)
                                    where we want a free-form paragraph.

  call_deepseek_with_tools(...)  — function-tool mode. Used by the
                                    per-tick trader decision flow
                                    (agent.decision.runtime).

Stateless, synchronous. Transport is litellm.completion, which gives a
single interface over OpenAI / DeepSeek / Kimi (Moonshot) / Anthropic / any
OpenAI-compatible endpoint. We route through litellm's OpenAI-compatible
handler (model="openai/<model>", api_base=<base_url>) so the existing
(base_url, api_key, model) contract is preserved unchanged: DeepSeek, Kimi
and others are reached via their OpenAI-compatible base URLs.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import litellm

# Keep stdout pristine — runner_cli.py speaks JSON-over-stdout, so litellm must
# not print banners/debug there. (litellm logs to stderr, which the runner
# forwards to its own stderr.)
litellm.telemetry = False
litellm.suppress_debug_info = True
# Silently drop provider-unsupported kwargs (e.g. `thinking`, `response_format`)
# instead of raising, so the same call works across providers.
litellm.drop_params = True


def _route(model: str) -> str:
    """Map a bare model id to litellm's OpenAI-compatible route.

    Already-namespaced ids (e.g. "deepseek/deepseek-chat", "anthropic/...")
    are passed through untouched; bare ids go through the OpenAI-compatible
    handler so they resolve against the supplied api_base.
    """
    return model if "/" in model else f"openai/{model}"


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

    `response_format={"type": "json_object"}` available for callers that
    need strict-JSON mode (dropped automatically if the provider lacks it).
    """
    kwargs: dict[str, Any] = {
        "model": _route(model),
        "api_key": api_key,
        "temperature": temperature,
        "timeout": timeout,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    # Only pin api_base for OpenAI-compatible endpoints; litellm-native,
    # provider-prefixed models (e.g. "anthropic/…") use the provider default.
    if base_url:
        kwargs["api_base"] = base_url
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = litellm.completion(**kwargs)
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
        "tool_calls": [ ... ],               # all calls
        "text": str,                         # LLM prose (often empty when tool was called)
        "prompt_tokens": int,
        "completion_tokens": int,
        "raw": str,                          # full response JSON
      }
    """
    kwargs: dict[str, Any] = {
        "model": _route(model),
        "api_key": api_key,
        "temperature": temperature,
        "timeout": timeout,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "tools": tools,
        "tool_choice": tool_choice,
    }
    if base_url:
        kwargs["api_base"] = base_url
    # `thinking` toggles DeepSeek's hybrid reasoning mode. None keeps the API
    # default; True/False force enabled/disabled. Forwarded as a provider-
    # specific extra param (dropped for providers that don't support it).
    if thinking is not None:
        kwargs["extra_body"] = {
            "thinking": {"type": "enabled" if thinking else "disabled"}
        }
    resp = litellm.completion(**kwargs)
    msg = resp.choices[0].message
    usage = resp.usage

    # Expose ALL tool calls (not just the first). The `update_belief` tool can
    # be paired with a trade tool in the same response — the runtime composes
    # them. `tool_call` points at the first non-`update_belief` call (or the
    # first call if all are belief updates) so legacy callers keep working.
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
