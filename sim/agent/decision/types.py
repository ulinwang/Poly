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
    yes_bid_depth: list[dict] | None = None
    yes_ask_depth: list[dict] | None = None
    no_bid_depth: list[dict] | None = None
    no_ask_depth: list[dict] | None = None
    yes_order_imbalance: float | None = None
    no_order_imbalance: float | None = None
    recent_fills: list[dict] | None = None

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
    # v10.1: recent decision log entries (most-recent-last). Each entry
    # is a small dict {"tick", "action", "outcome", "side", "price",
    # "size_usd", "fills", "yes_mid_after"}. The observer caps this
    # at MEMORY_DEPTH ≈ 3 to keep the prompt small.
    recent_decisions: list[dict] | None = None
    resting_orders: list[dict] | None = None
    recent_own_fills: list[dict] | None = None
    # v13 (AGT-4): the agent's most recent posterior on P(YES) as set
    # by an `update_belief` tool call. Shape:
    # {"yes_prob": float, "confidence": float, "set_at_tick": int,
    #  "rationale": str}. None until the agent first calls update_belief.
    belief_snapshot: dict | None = None
    # v15 (FORUM): the agent's structured social memory, surfaced so the
    # prompt builder can render a bounded "social memory" section.
    #   social_my_posts:   [{tick, post_id, content}]
    #   social_read_posts: [{tick, post_id, author_id, content, followed}]
    #   social_following:  [agent_id, ...]
    # All capped by the observer; followed authors are prioritised in
    # social_read_posts (see environment.env._fold_social_memory).
    social_my_posts: list[dict] | None = None
    social_read_posts: list[dict] | None = None
    social_following: list[int] | None = None


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
    # v13 (AGT-4): if the LLM called `update_belief` (either alone or
    # in combination with a trade tool), this holds the posterior to
    # be persisted onto the agent before applying the trade.
    # Shape: {"yes_prob": float, "confidence": float, "rationale": str}.
    belief_update: dict | None = None
    # v15 (FORUM): what the agent did on the social forum during this
    # tick's bounded loop, so the env can fold it into the agent's
    # structured social memory. Shape:
    #   {"posts":   [{"tick", "post_id", "content"}],
    #    "reads":   [{"tick", "post_id", "author_id", "content", "followed"}],
    #    "follows": [target_agent_id, ...]}
    # None when the forum was inactive this tick.
    forum_activity: dict | None = None
