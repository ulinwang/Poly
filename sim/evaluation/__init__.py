"""Evaluation layer for the simulation (the "eval" concept).

Two concerns:

  metrics  — raw measurements taken during a run (live, per tick / per agent).
  eval     — scored, post-hoc judgments built on those metrics (price-path
             calibration vs the real market, per-agent / per-persona PnL).

`schema` holds the data structures shared by the live stream (consumed by the
web observation page) and the post-hoc analysis in
`research/experiments/analysis`. `evaluation.metrics.macro` /
`evaluation.metrics.micro` compute them from simulation state.

Named `evaluation` (not `eval`) to avoid shadowing the Python builtin, since
the monorepo exposes packages under sim/ as top-level imports.
"""
from evaluation.schema import (
    TickMetrics,
    AgentSnapshot,
    MarketEval,
    AgentEval,
    ExperimentEval,
)

__all__ = [
    "TickMetrics",
    "AgentSnapshot",
    "MarketEval",
    "AgentEval",
    "ExperimentEval",
]
