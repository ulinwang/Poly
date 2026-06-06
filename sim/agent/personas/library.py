"""Hand-coded persona archetypes — REGISTRY ONLY in v8.

v7 deleted the legacy SkepticalEngineer/LotteryPlayer/etc. fixtures.
This module now exposes only an empty registry; populate it in v9 if
you need an alternate (non-calibrated) population. The factory still
defaults to the calibrated path.
"""
from __future__ import annotations

from agent.personas.persona import Persona


PERSONAS: dict[str, Persona] = {}


def register(name: str, persona: Persona) -> None:
    """Add a hand-coded persona to the registry."""
    if name in PERSONAS:
        raise ValueError(f"persona {name!r} already registered")
    PERSONAS[name] = persona


def get(name: str) -> Persona:
    if name not in PERSONAS:
        raise KeyError(
            f"unknown persona {name!r}; v8 ships an empty library — "
            f"register your archetype via library.register(...) first"
        )
    return PERSONAS[name]
