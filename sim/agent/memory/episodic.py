"""Cross-tick agent state — v8 stub.

Holds memory carried between `decide()` calls (e.g., recent decisions,
unresolved beliefs). v7 environment-side simulator scattered this
state across `Sim.agents[i].cash` and friends; v8 keeps that physical
state in `environment.env` and uses this module for decision-side
memory only.

`EpisodicMemory` is a placeholder dataclass; populating cross-tick
memory is a v9 concern (e.g., Bayesian belief update on observed
trades). Right now agents are stateless across calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EpisodicMemory:
    """Per-agent rolling state. v8 minimal: just the recent decision
    log + a private belief that may diverge from the prior. Future
    fields (v9): observed-trade counts, regret signals, peer-imitation
    cues."""
    agent_id: int
    recent_decisions: list[dict] = field(default_factory=list)
    private_belief_mu: float = 0.5
    private_belief_sigma: float = 0.2
    last_action_tick: int = -1

    def remember(self, tick: int, decision: dict) -> None:
        self.recent_decisions.append({"tick": tick, **decision})
        if len(self.recent_decisions) > 32:
            self.recent_decisions = self.recent_decisions[-32:]
        self.last_action_tick = tick
