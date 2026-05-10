"""Agent: features → personas → prompt → decision → memory.

Public API mirrors the v8 plan §2:

    from agent.factory import init_agents, AgentInit
    from agent.personas import Persona
    from agent.decision import decide, MarketSnapshot, AgentSnapshot
    from agent.features import build_features, derive_priors

`agent` reads ONLY through `data.query.*` — no direct ClickHouse
access. The Gym-style environment (Stage 3) provides the per-tick
state via `MarketSnapshot` / `AgentSnapshot`.
"""
from agent.personas.persona import Persona
from agent.factory import AgentInit, init_agents

__all__ = ["AgentInit", "init_agents", "Persona"]
