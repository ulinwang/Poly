"""Shared helpers for unit tests.

Centralizes construction of test fixtures so we don't depend on the
deleted hardcoded personas (SKEPTICAL_ENGINEER etc.) that v7 removed
from `src.agent.persona`.
"""
from __future__ import annotations

from agent.factory import AgentInit
from agent.personas.persona import Persona


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


def make_test_population(n: int) -> list[AgentInit]:
    """N deterministic AgentInit rows for tests that construct PolyEnv."""
    return [
        AgentInit(
            wallet_addr=f"0x{i:040x}",
            persona_type="Test",
            capital_initial=1000.0,
            profile_text="test trader",
            private_signal_mu=0.5,
            private_signal_sigma=0.1,
            risk_aversion=0.5,
            src_tx_count=0,
            src_maker_ratio=0.0,
            src_avg_position_usd=0.0,
            src_asset_diversity=0,
        )
        for i in range(n)
    ]
