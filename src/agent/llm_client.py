"""DeepSeek chat-completions client.

Single function `call_deepseek` consumed by both the per-tick agent
decision flow (`src.agent.decision`) and the persona text generator
(`src.population.persona_generator`). Stateless and synchronous.

Why this is its own module:
- Decouples the LLM call from any specific prompt or persona logic.
- Lets us swap the backend (different model / different OpenAI-
  compatible endpoint) by changing one file.
- Keeps the rest of the simulator free of `urllib` / HTTP concerns.
"""
from __future__ import annotations

import json
import urllib.request


def call_deepseek(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    timeout: float = 60.0,
    response_format: dict | None = None,
) -> dict:
    """Send one chat-completion request. Returns dict with keys:
    text, prompt_tokens, completion_tokens, raw.

    `response_format`:
      None (default) → free-form text. Use for natural-language tasks
        like persona profile generation.
      {"type": "json_object"} → DeepSeek will refuse to return text not
        parseable as JSON, AND requires the prompt to literally contain
        the word 'JSON'. Use for structured agent decisions.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    payload: dict = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if response_format is not None:
        payload["response_format"] = response_format
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    choice = obj["choices"][0]
    return {
        "text": choice["message"]["content"],
        "prompt_tokens": int(obj.get("usage", {}).get("prompt_tokens", 0)),
        "completion_tokens": int(obj.get("usage", {}).get("completion_tokens", 0)),
        "raw": raw,
    }
