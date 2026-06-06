"""Persona dataclass — pure data, no template logic.

Hand-coded archetypes from v2/v3 are not stored here; v7 dropped them.
The current `persona_type` is "Calibrated" for every wallet-anchored
agent built by `agent.factory.init_agents`. New archetypes (if any
land in v9) go in `agent/personas/library.py`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    persona_type: str
    risk_aversion: float
    capital_initial: float
    profile_text: str
