"""Static HTML report generator for output/<exp_id>/.

Public API:
    build_report(exp_dir)   → write exp_dir/report.html, return path
    build_for_latest(base)  → same, for the most recently modified dir

CLI:
    python -m viz <exp_id>
    python -m viz --latest
"""
from viz.report import build_for_latest, build_report

__all__ = ["build_report", "build_for_latest"]
