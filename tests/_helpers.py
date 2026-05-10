"""Shared helpers for unit tests.

Centralizes construction of test fixtures so we don't depend on the
deleted hardcoded personas (SKEPTICAL_ENGINEER etc.) that v7 removed
from `src.agent.persona`.
"""
from __future__ import annotations

from src.agent.persona import Persona


def make_test_personas(n: int) -> list[Persona]:
    """N identical neutral test personas. Use only in tests where
    persona shape doesn't matter (most env / orderbook tests just
    need a population of agents to run the engine)."""
    return [
        Persona(
            persona_type="Test",
            risk_aversion=0.5,
            capital_initial=1000.0,
            profile_text="test trader",
        )
        for _ in range(n)
    ]
