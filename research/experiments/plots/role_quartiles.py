"""Fig 04 — SERD ROI by quartile role.
   Fig 04b (vs baseline) → fig5_serd_vs_baseline."""
from experiments.plots._shared import (
    fig4_serd_roi as render,
    fig5_serd_vs_baseline as render_vs_baseline,
)

__all__ = ["render", "render_vs_baseline"]
