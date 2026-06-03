"""Nature-style figure preamble + helpers for the thesis figure pipeline.

Loaded by `scripts/thesis_figures.py` and `scripts/thesis_extra_artifacts.py`.
Encapsulates the publication-style settings, semantic palette, sizing
conventions, and a `finalize` helper that exports SVG + PDF + TIFF
alongside the embedded PNG and writes a sibling source-data CSV.

Conventions:
  - Times New Roman first for Latin text, then Songti SC / STSong for Chinese;
    editable text in SVG (`svg.fonttype='none'`) and TrueType in PDF
    (`pdf.fonttype=42`).
  - Only the left and bottom spines drawn; no grid.
  - 7.5 pt body text, 0.8 pt axis lines — sized for the thesis A4 page
    after embedding at ~12–15 cm wide.
  - Semantic palette:
        BLUE   = proposed / key treatment
        GREEN  = positive / improvement
        RED    = problem / regression / target outcome
        NEUTRAL_* = controls and reference
        TEAL/VIOLET = secondary signal families
"""
from __future__ import annotations

from pathlib import Path
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.text import Text
import pandas as pd


# --- Palette (subset of references/api.md PALETTE) ----------------------------
BLUE = "#0F4D92"           # 主对象 / 提议方法
BLUE_LIGHT = "#3775BA"
GREEN = "#8BCF8B"          # 改善 / 正向
GREEN_DEEP = "#5DA85E"
RED = "#B64342"            # 问题 / 偏离
RED_LIGHT = "#E9A6A1"
NEUTRAL_LIGHT = "#CFCECE"
NEUTRAL_MID = "#767676"
NEUTRAL_DARK = "#4D4D4D"
NEUTRAL_BLACK = "#272727"
TEAL = "#42949E"
VIOLET = "#9A4D8E"
GOLD = "#D4A93B"

DEFAULT_COLORS = [BLUE, GREEN, RED, TEAL, VIOLET, NEUTRAL_LIGHT]

# macOS ships Songti SC / STSong. With Times New Roman first, Latin text uses
# Times while Chinese glyphs fall back to Songti in mixed labels.
LATIN_FONTS = ["Times New Roman", "DejaVu Serif"]
CJK_FONTS = ["Songti SC", "Arial Unicode MS"]
CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def apply_style(font_size: float = 7.5, axes_lw: float = 0.8) -> None:
    """Apply Nature-style rcParams. Call once at module import time."""
    plt.rcParams.update({
        # MANDATORY: editable text in vector exports
        "font.family": "serif",
        "font.serif": LATIN_FONTS,
        "axes.unicode_minus": False,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        # Sizing
        "font.size": font_size,
        "axes.labelsize": font_size,
        "axes.titlesize": font_size + 0.5,
        "xtick.labelsize": font_size - 0.5,
        "ytick.labelsize": font_size - 0.5,
        "legend.fontsize": font_size - 0.5,
        # Spines + ticks
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": axes_lw,
        "xtick.major.width": axes_lw,
        "ytick.major.width": axes_lw,
        "xtick.major.size": 3.0,
        "ytick.major.size": 3.0,
        "axes.grid": False,
        # Legend
        "legend.frameon": False,
        "legend.handlelength": 1.6,
        "legend.borderpad": 0.3,
        # Lines
        "lines.linewidth": 1.0,
        "lines.markersize": 3.5,
        # Layout
        "figure.dpi": 150,
        "savefig.dpi": 600,
        "savefig.bbox": "tight",
        "savefig.transparent": False,
    })


def apply_text_fonts(fig) -> None:
    """Use Songti for Chinese text and Times New Roman for Latin-only text."""
    for text in fig.findobj(match=Text):
        props = text.get_fontproperties().copy()
        if CJK_RE.search(text.get_text() or ""):
            props.set_family(CJK_FONTS)
        else:
            props.set_family(LATIN_FONTS)
        text.set_fontproperties(props)


# --- Sizing helpers -----------------------------------------------------------
MM_PER_INCH = 25.4


def in_(mm: float) -> float:
    return mm / MM_PER_INCH


def fig_size(width_mm: float, height_mm: float) -> tuple[float, float]:
    return (in_(width_mm), in_(height_mm))


COL_SINGLE_MM = 89.0      # Nature single column
COL_DOUBLE_MM = 183.0     # Nature double column
STACK_PANEL_MM = 58.0     # height per stacked panel (top-bottom layout)


def fig_size_vstack(n_panels: int, width_mm: float = COL_DOUBLE_MM,
                    panel_mm: float = STACK_PANEL_MM) -> tuple[float, float]:
    """Figure size for vertically stacked panels (same width, taller)."""
    return fig_size(width_mm, panel_mm * n_panels)


# --- Panel label --------------------------------------------------------------
def panel_label(ax, label: str, x: float = -0.16, y: float = 1.05,
                fontsize: float = 9.0):
    ax.text(x, y, label, transform=ax.transAxes,
            fontsize=fontsize, fontweight="bold", ha="left", va="bottom")


# --- finalize -----------------------------------------------------------------
def finalize(fig, base_path: Path, source_data: pd.DataFrame | None = None,
             formats: tuple[str, ...] = ("png", "svg", "pdf", "tiff"),
             pad: float = 0.4) -> dict:
    """Save the figure in publication formats + sibling source data.

    Returns the dict of created file paths.
    """
    out: dict[str, str] = {}
    base_path = Path(base_path)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    apply_text_fonts(fig)
    fig.tight_layout(pad=pad)
    for fmt in formats:
        dpi = 600 if fmt == "tiff" else None
        p = base_path.with_suffix(f".{fmt}")
        kw = {}
        if dpi is not None:
            kw["dpi"] = dpi
        fig.savefig(p, **kw)
        out[fmt] = str(p)
    if source_data is not None:
        data_dir = base_path.parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        csv_path = data_dir / (base_path.stem + ".csv")
        source_data.to_csv(csv_path, index=False)
        out["data"] = str(csv_path)
    plt.close(fig)
    return out
