#!/usr/bin/env python3
"""Agent introspection: dump the LLM tool schemas and prompt templates as JSON.

Single source of truth for the web "Agent" tab. Running

    python sim/agent/introspect.py

prints one JSON object to stdout:

    {
      "tools": [...],              # TOOL_SCHEMAS (name / description / parameters)
      "prompt_templates": {...}    # the system / user prompt templates + a sample
    }

The tool list is read straight from ``agent.decision.tool_schemas.TOOL_SCHEMAS``
so it never drifts from what the model actually sees. The prompt templates are
read from ``agent/personas/templates/`` (the same files ``prompt.builder``
renders at runtime). Because the production prompts are assembled dynamically
(Jinja2 + persona/state injection), we expose the raw template text per segment
plus a single example render so the UI can show a realistic, readable prompt.

This is read-only: it imports schemas and reads template files, never touching
ClickHouse, the network, or any run state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from agent.decision.tool_schemas import TOOL_SCHEMAS

_TEMPLATE_DIR = (
    Path(__file__).resolve().parent / "personas" / "templates"
)


def _read_template(name: str) -> str:
    """Return the raw text of a template file, or an empty string if missing."""
    path = _TEMPLATE_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _dump_tools() -> list[dict]:
    """Flatten TOOL_SCHEMAS to {name, description, parameters} entries.

    Each tool in TOOL_SCHEMAS is an OpenAI-style ``{"type": "function",
    "function": {...}}`` envelope; we unwrap the ``function`` body so the
    UI gets a flat shape.
    """
    out: list[dict] = []
    for entry in TOOL_SCHEMAS:
        fn = entry.get("function", {})
        out.append(
            {
                "name": fn.get("name", ""),
                "description": (fn.get("description") or "").strip(),
                "parameters": fn.get("parameters", {}),
            }
        )
    return out


def _sample_render() -> str:
    """Build one concrete example of the production system + user prompt.

    Uses ``prompt.builder`` with a tiny synthetic persona / market / agent
    snapshot so the rendered text matches what an agent actually receives.
    Falls back to a short note if the builder cannot be imported (e.g. a
    missing optional dependency); the raw segments are still exposed.
    """
    try:
        from agent.personas.persona import Persona
        from agent.decision.types import AgentSnapshot, MarketSnapshot
        from agent.prompt.builder import (
            build_clob_system_prompt,
            build_user_prompt,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return f"(sample render unavailable: {exc})"

    try:
        persona = Persona(
            persona_type="Archetype",
            risk_aversion=0.6,
            capital_initial=1000.0,
            profile_text=(
                "A disciplined value trader who waits for clear mispricings "
                "and sizes positions conservatively."
            ),
        )
        system = build_clob_system_prompt(
            persona,
            question="Will it rain in NYC tomorrow?",
            description="Resolves YES if measurable precipitation is recorded.",
            end_date="2026-12-31",
            tick_size=0.01,
        )
        market = MarketSnapshot(
            yes_best_bid=0.48,
            yes_best_ask=0.52,
            yes_mid=0.50,
            no_best_bid=0.48,
            no_best_ask=0.52,
            no_mid=0.50,
            yes_mid_history=[0.49, 0.50, 0.50],
            total_ticks=20,
            ticks_remaining=15,
        )
        agent = AgentSnapshot(
            agent_id=1,
            cash=1000.0,
            yes_shares=0.0,
            no_shares=0.0,
            n_resting_orders=0,
        )
        user = build_user_prompt(market, agent)
        return (
            "=== SYSTEM PROMPT (example render) ===\n\n"
            f"{system}\n\n"
            "=== USER PROMPT (example render) ===\n\n"
            f"{user}"
        )
    except Exception as exc:  # pragma: no cover - depends on dataclass shape
        return f"(sample render unavailable: {exc})"


def dump() -> dict:
    """Assemble and print the introspection payload as JSON to stdout."""
    payload = {
        "tools": _dump_tools(),
        "prompt_templates": {
            "clob_system": {
                "title": "CLOB system prompt (v7, production)",
                "description": (
                    "Two-stage decision prompt shown once per agent. Both YES "
                    "and NO order books are visible; supports LIMIT / MARKET / "
                    "CANCEL / SPLIT / MERGE / HOLD. Rendered with Jinja2 from "
                    "templates/clob_system.j2, injecting the persona profile, "
                    "market question, resolution rules and tick size."
                ),
                "source": "sim/agent/personas/templates/clob_system.j2",
                "template": _read_template("clob_system.j2"),
            },
            "user_state": {
                "title": "User state prompt (per tick)",
                "description": (
                    "Re-rendered every tick from templates/user_state.j2 with "
                    "the live market snapshot (order books, depth, recent "
                    "fills) and the agent's own portfolio, resting orders, "
                    "stated belief and recent decisions."
                ),
                "source": "sim/agent/personas/templates/user_state.j2",
                "template": _read_template("user_state.j2"),
            },
            "system_base": {
                "title": "Legacy single-action system prompt (v2/v3)",
                "description": (
                    "Older single-side prompt kept for backwards compatibility. "
                    "Rendered via str.format from templates/system_base.txt; the "
                    "model returns a single JSON action instead of calling tools."
                ),
                "source": "sim/agent/personas/templates/system_base.txt",
                "template": _read_template("system_base.txt"),
            },
            "sample_render": {
                "title": "Example rendered prompt",
                "description": (
                    "A concrete render of the production system + user prompts "
                    "using a synthetic persona and market snapshot, to show what "
                    "an agent actually receives at decision time."
                ),
                "source": "sim/agent/prompt/builder.py",
                "template": _sample_render(),
            },
        },
    }
    json.dump(payload, fp=sys.stdout, ensure_ascii=False, indent=2)
    print()
    return payload


if __name__ == "__main__":
    dump()
