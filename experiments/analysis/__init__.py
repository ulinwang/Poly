"""Per-experiment post-hoc analysis.

    serd        — Structural Entropy Role Discovery (Gomez-Cram 2026)
    calibration — sim vs real price comparison metrics
    tables      — markdown + LaTeX paper tables
    pnl         — per-persona PnL aggregation (v9 stub)
"""
from experiments.analysis import serd, calibration, tables

__all__ = ["serd", "calibration", "tables"]
