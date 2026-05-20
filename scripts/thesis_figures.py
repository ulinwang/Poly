"""Generate thesis figures 1–7 from committed experiment artifacts.

Nature-style rendering: Arial sans-serif, editable SVG/PDF text,
semantic palette, no grid, only left + bottom spines, panel labels
where needed. Each figure is exported as PNG (for docx embed) +
SVG + PDF + 600-dpi TIFF, with a sibling CSV under figures/data/.

Run:  uv run python scripts/thesis_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _thesis_style import (
    apply_style, finalize, fig_size, panel_label,
    BLUE, BLUE_LIGHT, GREEN, GREEN_DEEP, RED, RED_LIGHT,
    NEUTRAL_LIGHT, NEUTRAL_MID, NEUTRAL_DARK, NEUTRAL_BLACK, TEAL, VIOLET,
    COL_SINGLE_MM, COL_DOUBLE_MM,
)

apply_style()

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "v13" / "figures"
OUT.mkdir(parents=True, exist_ok=True)


def _eid(suite, name):
    idx = json.loads((ROOT / f"output_v13/{suite}/index.json").read_text())
    for r in idx["runs"]:
        if r["name"] == name:
            return r["exp_id"]
    raise KeyError(name)


def _acts(suite, name):
    return pd.read_parquet(
        ROOT / f"output_v13/{suite}/{_eid(suite, name)}/raw/agent_actions.parquet"
    ).sort_values("tick_idx")


def _yseries(suite, name):
    a = _acts(suite, name)
    s = a.groupby("tick_idx")["yes_mid_after"].last()
    return s.index.to_numpy(), s.to_numpy()


# ----------------------------------------------------------------------
# Fig 1 — schematic of the simulation loop
# ----------------------------------------------------------------------

def fig1_schematic():
    fig, ax = plt.subplots(figsize=fig_size(160, 50))
    ax.axis("off")
    boxes = [
        (0.02, "Real wallet\nhistory\n(pre-event)"),
        (0.21, "Behavioral\nprofile +\ninitial belief"),
        (0.40, "LLM agent\ndecision\n(per round)"),
        (0.59, "Continuous\ndouble-auction\nmatching"),
        (0.78, "Market price\n+ outcome\nsettlement"),
    ]
    for x, t in boxes:
        ax.add_patch(plt.Rectangle((x, 0.32), 0.17, 0.42,
                     fill=False, ec=NEUTRAL_BLACK, lw=0.9))
        ax.text(x + 0.085, 0.53, t, ha="center", va="center", fontsize=7)
    for x in (0.19, 0.38, 0.57, 0.76):
        ax.annotate("", (x + 0.02, 0.53), (x, 0.53),
                    arrowprops=dict(arrowstyle="-|>", color=NEUTRAL_BLACK, lw=0.9))
    ax.annotate("", (0.49, 0.32), (0.66, 0.32),
                arrowprops=dict(arrowstyle="-|>", color=NEUTRAL_MID, lw=0.7,
                                connectionstyle="arc3,rad=0.4"))
    ax.text(0.575, 0.16, "next round: updated state + memory",
            ha="center", fontsize=6.5, color=NEUTRAL_MID, style="italic")
    ax.set_xlim(0, 0.97); ax.set_ylim(0, 0.85)
    finalize(fig, OUT / "fig1_loop")


# ----------------------------------------------------------------------
# Fig 2 — seed noise floor
# ----------------------------------------------------------------------

def fig2_seed():
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM, 65))
    seed_colors = [BLUE, TEAL, VIOLET]
    rows = []
    for s in (0, 1, 2):
        t, y = _yseries("b2", f"b2_s{s}")
        ax.plot(t, y, marker="o", ms=2.2, lw=1.0,
                color=seed_colors[s], label=f"seed {s}")
        for ti, yi in zip(t, y):
            rows.append({"seed": s, "round": int(ti), "yes_mid": float(yi)})
    ax.axhline(0.155, color=NEUTRAL_MID, ls="--", lw=0.7, label="start 0.155")
    ax.set_xlabel("round"); ax.set_ylabel("YES mid-price")
    ax.set_ylim(0.05, 0.40)
    ax.legend(loc="upper left", fontsize=6)
    finalize(fig, OUT / "fig2_seed", source_data=pd.DataFrame(rows))


# ----------------------------------------------------------------------
# Fig 3 — population structure (B3)
# ----------------------------------------------------------------------

def fig3_population():
    groups = {"cluster\narchetype": [], "marginal\nrandom": [],
              "uniform\nrandom": []}
    key_map = {"cluster\narchetype": "archetype",
               "marginal\nrandom": "marginal",
               "uniform\nrandom": "uniform"}
    for label, key in key_map.items():
        for s in (0, 1, 2):
            _, y = _yseries("b3", f"b3_{key}_s{s}")
            groups[label].append(float(y[-1]))
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM, 60))
    xs = np.arange(len(groups))
    means = [np.mean(v) for v in groups.values()]
    sds = [np.std(v, ddof=1) for v in groups.values()]
    colors = [BLUE, NEUTRAL_LIGHT, NEUTRAL_LIGHT]
    ax.bar(xs, means, yerr=sds, width=0.55, color=colors,
           edgecolor=NEUTRAL_BLACK, linewidth=0.7,
           error_kw=dict(elinewidth=0.7, capthick=0.7, capsize=3))
    for i, vals in enumerate(groups.values()):
        ax.scatter([i] * 3, vals, color=NEUTRAL_BLACK, s=8, zorder=3,
                   edgecolor="white", linewidth=0.4)
    ax.axhline(0.155, color=NEUTRAL_MID, ls="--", lw=0.7)
    ax.text(2.55, 0.155, "start", color=NEUTRAL_MID, fontsize=6,
            va="center", ha="left")
    ax.set_xticks(xs); ax.set_xticklabels(groups.keys())
    ax.set_ylabel("final YES mid-price")
    ax.set_ylim(0, 0.42)
    rows = [{"group": k, "values": v} for k, v in groups.items()]
    df = pd.DataFrame([
        {"group": k.replace("\n", " "),
         "mean": np.mean(v), "std": np.std(v, ddof=1),
         "values": ";".join(f"{x:.3f}" for x in v)}
        for k, v in groups.items()
    ])
    finalize(fig, OUT / "fig3_population", source_data=df)


# ----------------------------------------------------------------------
# Fig 4 — belief mechanism action structure (B4)
# ----------------------------------------------------------------------

def fig4_belief():
    def mix(name):
        a = _acts("b4", name)
        v = a.action_type.value_counts(normalize=True)
        return (100 * v.get("CANCEL", 0), 100 * v.get("HOLD", 0),
                100 * v.get("UPDATE_BELIEF", 0))
    off = np.mean([mix(f"b4_belief_off_s{s}") for s in (0, 1, 2)], axis=0)
    on = np.mean([mix(f"b4_belief_on_s{s}") for s in (0, 1, 2)], axis=0)
    labels = ["cancels", "idle holds", "belief\nstatements"]
    x = np.arange(3); w = 0.36
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM + 10, 60))
    bars1 = ax.bar(x - w / 2, off, w, label="belief tool off",
                   color=NEUTRAL_LIGHT, edgecolor=NEUTRAL_BLACK, linewidth=0.7)
    bars2 = ax.bar(x + w / 2, on, w, label="belief tool on",
                   color=BLUE, edgecolor=NEUTRAL_BLACK, linewidth=0.7)
    for bars, vals in [(bars1, off), (bars2, on)]:
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.0,
                    f"{v:.1f}", ha="center", va="bottom", fontsize=6)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("share of all actions (%)")
    ax.set_ylim(0, max(on.max(), off.max()) + 8)
    ax.legend(loc="upper left", fontsize=6)
    df = pd.DataFrame({"label": labels, "off_pct": off, "on_pct": on})
    finalize(fig, OUT / "fig4_belief", source_data=df)


# ----------------------------------------------------------------------
# Fig 5 — information shock: flow + entropy (B6) — two panels
# ----------------------------------------------------------------------

def fig5_shock():
    import sys
    sys.path.insert(0, str(ROOT))
    from experiments.analysis.network import build_network
    def stat(name):
        eid = _eid("b6", name)
        f = pd.read_parquet(
            ROOT / f"output_v13/b6/{eid}/raw/agent_fills.parquet")
        g = build_network(f, exclude_env_maker=True)
        w = np.array([d["weight"] for *_, d in g.edges(data=True)], float)
        p = w / w.sum() if w.sum() else w
        H = float(-(p * np.log(p)).sum()) if len(p) else 0.0
        return float(w.sum()), H
    ctrl = [stat(f"b6_control_s{s}") for s in (0, 1, 2)]
    rumor = [stat(f"b6_rumor_s{s}") for s in (0, 1, 2)]
    ctrl_f = np.array([c[0] for c in ctrl]); ctrl_h = np.array([c[1] for c in ctrl])
    rum_f = np.array([c[0] for c in rumor]); rum_h = np.array([c[1] for c in rumor])
    fig, axes = plt.subplots(1, 2, figsize=fig_size(COL_DOUBLE_MM - 30, 60))
    for ax, c_vals, r_vals, ylabel in [
        (axes[0], ctrl_f, rum_f, "total capital flow (USD)"),
        (axes[1], ctrl_h, rum_h, "structural entropy")
    ]:
        means = [c_vals.mean(), r_vals.mean()]
        sds = [c_vals.std(ddof=1), r_vals.std(ddof=1)]
        ax.bar([0, 1], means, yerr=sds, width=0.5,
               color=[NEUTRAL_LIGHT, BLUE],
               edgecolor=NEUTRAL_BLACK, linewidth=0.7,
               error_kw=dict(elinewidth=0.7, capthick=0.7, capsize=3))
        ax.scatter([0] * 3, c_vals, color=NEUTRAL_BLACK, s=7, zorder=3,
                   edgecolor="white", linewidth=0.4)
        ax.scatter([1] * 3, r_vals, color=NEUTRAL_BLACK, s=7, zorder=3,
                   edgecolor="white", linewidth=0.4)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["control", "rumor"])
        ax.set_ylabel(ylabel)
    panel_label(axes[0], "a")
    panel_label(axes[1], "b")
    df = pd.DataFrame({
        "metric": ["flow"] * 6 + ["entropy"] * 6,
        "condition": (["control"] * 3 + ["rumor"] * 3) * 2,
        "value": np.concatenate([ctrl_f, rum_f, ctrl_h, rum_h]),
    })
    finalize(fig, OUT / "fig5_shock", source_data=df)


# ----------------------------------------------------------------------
# Fig 6 — B1 external validity (price moved toward truth?)
# ----------------------------------------------------------------------

def fig6_external():
    m = pd.read_csv(ROOT / "output_v13/b1_metrics.csv")
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM + 10, 60))
    for i, r in m.iterrows():
        c = GREEN_DEEP if bool(r["toward"]) else RED
        ax.annotate("", (1, r["yf"]), (0, r["y0"]),
                    arrowprops=dict(arrowstyle="-|>", color=c, lw=0.9,
                                    alpha=0.9))
    ax.scatter([1.08] * len(m), m["truth"], marker="*", s=44,
               color=NEUTRAL_BLACK, zorder=3,
               edgecolor="white", linewidth=0.4)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["start", "final"])
    ax.set_xlim(-0.05, 1.18); ax.set_ylim(-0.05, 1.05)
    ax.set_ylabel("YES mid-price")
    # direct labels (no legend)
    ax.text(0.55, 1.02, "moved toward truth", color=GREEN_DEEP,
            fontsize=6.5, ha="center")
    ax.text(0.55, -0.03, "moved away from truth", color=RED,
            fontsize=6.5, ha="center")
    ax.text(1.10, 1.0, "truth", fontsize=6, color=NEUTRAL_DARK, va="center")
    ax.scatter([1.085], [1.0], marker="*", s=18, color=NEUTRAL_BLACK,
               edgecolor="white", linewidth=0.3, zorder=4)
    finalize(fig, OUT / "fig6_external", source_data=m)


# ----------------------------------------------------------------------
# Fig 7 — signal-fix before/after
# ----------------------------------------------------------------------

def fig7_fix():
    def drifts(suite):
        out = []
        idx = json.loads((ROOT / f"output_v13/{suite}/index.json").read_text())
        for r in idx["runs"]:
            a = pd.read_parquet(
                ROOT / f"output_v13/{suite}/{r['exp_id']}/raw/agent_actions.parquet"
            ).sort_values("tick_idx")
            out.append(float(a["yes_mid_after"].iloc[-1])
                       - float(a["yes_mid_before"].iloc[0]))
        return out
    before, after = drifts("b2"), drifts("b2fix")
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM, 60))
    ax.bar([0, 1], [np.mean(before), np.mean(after)],
           yerr=[np.std(before, ddof=1), np.std(after, ddof=1)],
           width=0.5, color=[RED, GREEN_DEEP],
           edgecolor=NEUTRAL_BLACK, linewidth=0.7,
           error_kw=dict(elinewidth=0.7, capthick=0.7, capsize=3))
    ax.scatter([0] * 3, before, color=NEUTRAL_BLACK, s=8, zorder=3,
               edgecolor="white", linewidth=0.4)
    ax.scatter([1] * 3, after, color=NEUTRAL_BLACK, s=8, zorder=3,
               edgecolor="white", linewidth=0.4)
    ax.axhline(0, color=NEUTRAL_MID, lw=0.7)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["before fix", "after fix"])
    ax.set_ylabel("price drift (final − start)")
    df = pd.DataFrame({"condition": ["before"] * 3 + ["after"] * 3,
                       "drift": before + after})
    finalize(fig, OUT / "fig7_fix", source_data=df)


def main():
    fig1_schematic()
    fig2_seed()
    fig3_population()
    fig4_belief()
    fig5_shock()
    fig6_external()
    fig7_fix()
    print("wrote figures 1-7 to", OUT)


if __name__ == "__main__":
    main()
