"""Polymarket simulation environment.

Public API:
    PolyEnv               — Gym-style env with reset/step/state/settle
    make_sim              — direct Simulation builder (legacy v7 path)
    seed_orderbook_liquidity, ENV_MAKER_AGENT_ID
    Simulation, AgentRuntime
    settle                — re-export of environment.settlement.settle

Tools / observers / seeders are sub-packages — import them as
`from environment.tools import place_order` etc.
"""
from environment.env import (
    AgentRuntime, ENV_MAKER_AGENT_ID, PolyEnv, Simulation,
    make_sim, seed_orderbook_liquidity, settle,
    run_simulation,
)
from environment.orderbook import OrderBook, Fill

__all__ = [
    "AgentRuntime", "ENV_MAKER_AGENT_ID", "PolyEnv", "Simulation",
    "make_sim", "seed_orderbook_liquidity", "settle",
    "run_simulation",
    "OrderBook", "Fill",
]
