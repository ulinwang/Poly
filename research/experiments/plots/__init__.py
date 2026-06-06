"""Per-figure modules + the legacy `main()` driver.

Each figure module exposes a `render(...)` callable. The runner
calls them in numeric order to produce `output/<exp_id>/figure/0N_*.png`.
"""
from experiments.plots._shared import main, _save, _no_data_panel

__all__ = ["main", "_save", "_no_data_panel"]
