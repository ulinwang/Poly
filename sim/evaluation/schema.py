"""Data structures for simulation metrics and evals.

LIVE (streamed each tick during a run → web observation page):
  - TickMetrics   : one row per tick, market/macro level.
  - AgentSnapshot : one row per agent per tick, micro level.

POST-HOC (computed once at the end → reports / paper tables):
  - MarketEval     : macro scorecard for the whole run.
  - AgentEval      : micro scorecard per agent.
  - ExperimentEval : MarketEval + [AgentEval] + per-persona rollups.

All are plain dataclasses; use dataclasses.asdict() to serialize to the
JSON the runner emits and the analysis layer consumes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────── LIVE / per-tick ───────────────────────────

@dataclass
class TickMetrics:
    """Macro (market-price) snapshot for a single tick."""
    tick: int
    yes_mid: float
    no_mid: float
    # Deviation from the YES+NO=1 arbitrage parity; |gap| large ⇒ inefficiency.
    parity_gap: float
    # Fills that happened during this tick.
    n_fills: int
    # YES-mid change vs the previous tick (per-tick return).
    ret: float


@dataclass
class AgentSnapshot:
    """Micro (single-agent) snapshot for a single tick."""
    tick: int
    agent_id: int
    persona: str
    cash: float
    cash_reserved: float
    pos_yes: float
    pos_no: float
    # Agent's stated posterior P(YES) and confidence, if it set one (else None).
    belief_yes: Optional[float]
    belief_conf: Optional[float]
    # Mark-to-market PnL vs initial capital at the current mids.
    pnl: float


# ─────────────────────────── POST-HOC / evals ──────────────────────────

@dataclass
class MarketEval:
    """Macro scorecard for a finished run."""
    n_ticks: int
    final_yes_mid: float
    max_yes_mid: float
    min_yes_mid: float
    # Std of per-tick YES-mid returns (realized volatility).
    realized_vol: float
    # Calibration against the real Polymarket path (None if unavailable).
    pearson_r: Optional[float] = None
    mae: Optional[float] = None
    final_diff: Optional[float] = None
    direction_correct: Optional[bool] = None


@dataclass
class AgentEval:
    """Micro scorecard per agent for a finished run."""
    agent_id: int
    persona: str
    final_pnl: float
    n_trades: int
    win: Optional[bool] = None
    # |belief_yes − final_yes_mid| averaged over ticks the agent held a belief.
    belief_cal_err: Optional[float] = None
    # 'maker' | 'taker' | 'mixed' | None (from fill roles).
    role: Optional[str] = None


@dataclass
class ExperimentEval:
    """Full evaluation bundle for one experiment run."""
    market: MarketEval
    agents: list[AgentEval] = field(default_factory=list)
    # Per-persona PnL rollup: {persona: {n, mean, median, min, max}}.
    per_persona: dict = field(default_factory=dict)
