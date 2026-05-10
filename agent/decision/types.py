"""Per-tick dataclasses. Pure data, no behavior."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarketSnapshot:
    yes_best_bid: float | None
    yes_best_ask: float | None
    yes_mid: float
    no_best_bid: float | None
    no_best_ask: float | None
    no_mid: float
    yes_mid_history: list[float]
    ticks_remaining: int
    total_ticks: int

    @property
    def time_remaining_pct(self) -> float:
        return self.ticks_remaining / max(self.total_ticks, 1)


@dataclass
class AgentSnapshot:
    agent_id: int
    cash: float
    yes_shares: float
    no_shares: float
    n_resting_orders: int
    private_signal_mu: float | None = None
    private_signal_sigma: float | None = None


@dataclass
class Decision:
    order_type: str
    outcome: str
    side: str
    price: float
    size_usd: float
    reasoning: str
    raw_response: str
    api_latency_ms: int
    api_error: str
