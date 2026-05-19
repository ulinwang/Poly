"""Generate the thesis figures from committed experiment artifacts.

Writes black-and-white, caption-free PNGs to docs/v13/figures/. All
in-figure text is English/numeric (Chinese captions live in the docx);
this avoids CJK-font dependence and matches the reference format
(figure image + Chinese caption below).

    uv run python scripts/thesis_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "v13" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Serif",
    "font.size": 10,
    "axes.edgecolor": "#222",
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.color": "#ddd",
    "grid.linewidth": 0.5,
    "figure.dpi": 150,
    "savefig.bbox": "tight",
})
GRAY = "#888"
DARK = "#1a1a1a"
ACC = "#333"


def _eid(suite: str, name: str) -> str:
    idx = json.loads((ROOT / f"output_v13/{suite}/index.json").read_text())
    for r in idx["runs"]:
        if r["name"] == name:
            return r["exp_id"]
    raise KeyError(name)


def _acts(suite: str, name: str) -> pd.DataFrame:
    d = ROOT / f"output_v13/{suite}/{_eid(suite, name)}/raw/agent_actions.parquet"
    return pd.read_parquet(d).sort_values("tick_idx")


def _yseries(suite: str, name: str):
    a = _acts(suite, name)
    s = a.groupby("tick_idx")["yes_mid_after"].last()
    return s.index.to_numpy(), s.to_numpy()


# ---- 图1: schematic of the simulation loop --------------------------

def fig1_schematic():
    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    ax.axis("off")
    boxes = [
        (0.02, "Real wallet\nhistory\n(pre-event)"),
        (0.21, "Behavioral\nprofile +\ninitial belief"),
        (0.40, "LLM agent\ndecision\n(each round)"),
        (0.59, "Continuous\ndouble-auction\nmatching"),
        (0.78, "Market price\n+ outcome\nsettlement"),
    ]
    for x, t in boxes:
        ax.add_patch(plt.Rectangle((x, 0.30), 0.17, 0.42,
                     fill=False, ec=DARK, lw=1.1))
        ax.text(x + 0.085, 0.51, t, ha="center", va="center", fontsize=8.5)
    for x in (0.19, 0.38, 0.57, 0.76):
        ax.annotate("", (x + 0.02, 0.51), (x, 0.51),
                    arrowprops=dict(arrowstyle="-|>", color=DARK, lw=1))
    ax.annotate("", (0.485, 0.30), (0.665, 0.30),
                arrowprops=dict(arrowstyle="-|>", color=GRAY, lw=1,
                                connectionstyle="arc3,rad=0.4"))
    ax.text(0.575, 0.12, "next round: updated market state + memory",
            ha="center", fontsize=7.5, color=GRAY, style="italic")
    ax.set_xlim(0, 0.97); ax.set_ylim(0, 0.85)
    fig.savefig(OUT / "fig1_loop.png"); plt.close(fig)


# ---- 图2: B2 seed noise floor ---------------------------------------

def fig2_seed():
    fig, ax = plt.subplots(figsize=(6.0, 3.4))
    for s in (0, 1, 2):
        t, y = _yseries("b2", f"b2_s{s}")
        ax.plot(t, y, marker="o", ms=3, lw=1.2, color=DARK,
                label=f"seed {s}", alpha=0.55 + 0.15 * s)
    ax.axhline(0.155, color=GRAY, ls="--", lw=1, label="start price 0.155")
    ax.set_xlabel("round"); ax.set_ylabel("YES mid-price")
    ax.set_ylim(0, 0.4)
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(OUT / "fig2_seed.png"); plt.close(fig)


# ---- 图3: B3 population structure ------------------------------------

def fig3_population():
    groups = {"archetype": [], "marginal": [], "uniform": []}
    for g in groups:
        for s in (0, 1, 2):
            _, y = _yseries("b3", f"b3_{g}_s{s}")
            groups[g].append(y[-1])
    fig, ax = plt.subplots(figsize=(5.4, 3.4))
    xs = np.arange(3)
    means = [np.mean(groups[g]) for g in groups]
    sds = [np.std(groups[g], ddof=1) for g in groups]
    ax.bar(xs, means, yerr=sds, width=0.5, color="#bbb",
           edgecolor=DARK, capsize=4)
    for i, g in enumerate(groups):
        ax.scatter([i] * 3, groups[g], color=DARK, s=18, zorder=3)
    ax.axhline(0.155, color=GRAY, ls="--", lw=1)
    ax.set_xticks(xs)
    ax.set_xticklabels(["cluster\narchetype", "marginal\nrandom",
                        "uniform\nrandom"])
    ax.set_ylabel("final YES mid-price")
    ax.set_ylim(0, 0.42)
    fig.savefig(OUT / "fig3_population.png"); plt.close(fig)


# ---- 图4: B4 belief mechanism ---------------------------------------

def fig4_belief():
    def mix(name):
        a = _acts("b4", name)
        v = a.action_type.value_counts(normalize=True)
        return (100 * v.get("CANCEL", 0), 100 * v.get("HOLD", 0),
                100 * v.get("UPDATE_BELIEF", 0))
    off = np.mean([mix(f"b4_belief_off_s{s}") for s in (0, 1, 2)], axis=0)
    on = np.mean([mix(f"b4_belief_on_s{s}") for s in (0, 1, 2)], axis=0)
    labels = ["CANCEL %", "idle HOLD %", "belief-statement %"]
    x = np.arange(3); w = 0.36
    fig, ax = plt.subplots(figsize=(5.8, 3.4))
    ax.bar(x - w / 2, off, w, label="belief tool off",
           color="#ccc", edgecolor=DARK)
    ax.bar(x + w / 2, on, w, label="belief tool on",
           color="#666", edgecolor=DARK)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("share of actions (%)")
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(OUT / "fig4_belief.png"); plt.close(fig)


# ---- 图5: B6 information shock --------------------------------------

def fig5_shock():
    # entropy/flow precomputed in RESULTS; recompute flow from fills.
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
    ctrl = np.mean([stat(f"b6_control_s{s}") for s in (0, 1, 2)], axis=0)
    rumor = np.mean([stat(f"b6_rumor_s{s}") for s in (0, 1, 2)], axis=0)
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 3.2))
    axes[0].bar([0, 1], [ctrl[0], rumor[0]], width=0.5,
                color=["#ccc", "#666"], edgecolor=DARK)
    axes[0].set_xticks([0, 1]); axes[0].set_xticklabels(["control", "rumor"])
    axes[0].set_ylabel("total capital flow (USD)")
    axes[0].set_title("capital flow", fontsize=9)
    axes[1].bar([0, 1], [ctrl[1], rumor[1]], width=0.5,
                color=["#ccc", "#666"], edgecolor=DARK)
    axes[1].set_xticks([0, 1]); axes[1].set_xticklabels(["control", "rumor"])
    axes[1].set_ylabel("network structural entropy")
    axes[1].set_title("network topology", fontsize=9)
    fig.savefig(OUT / "fig5_shock.png"); plt.close(fig)


# ---- 图6: B1 external validity --------------------------------------

def fig6_external():
    m = pd.read_csv(ROOT / "output_v13/b1_metrics.csv")
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    y0 = m["y0"].to_numpy(); yf = m["yf"].to_numpy()
    truth = m["truth"].to_numpy()
    for i in range(len(m)):
        c = DARK if bool(m["toward"][i]) else GRAY
        ax.annotate("", (1, yf[i]), (0, y0[i]),
                    arrowprops=dict(arrowstyle="-|>", color=c, lw=1.1,
                                    alpha=0.8))
    ax.scatter([1.05] * len(m), truth, marker="*", s=80,
               color=DARK, zorder=3, label="true outcome")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["start", "final"])
    ax.set_xlim(-0.1, 1.25); ax.set_ylim(-0.05, 1.05)
    ax.set_ylabel("YES mid-price")
    ax.set_title("each arrow = one market (dark = moved toward truth)",
                 fontsize=8.5)
    fig.savefig(OUT / "fig6_external.png"); plt.close(fig)


# ---- 图7: signal-fix before/after -----------------------------------

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
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    ax.bar([0, 1], [np.mean(before), np.mean(after)],
           yerr=[np.std(before, ddof=1), np.std(after, ddof=1)],
           width=0.5, color=["#ccc", "#666"], edgecolor=DARK, capsize=4)
    ax.scatter([0] * 3, before, color=DARK, s=18, zorder=3)
    ax.scatter([1] * 3, after, color=DARK, s=18, zorder=3)
    ax.axhline(0, color=GRAY, lw=1)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["before fix", "after fix"])
    ax.set_ylabel("price drift vs start (final − start)")
    fig.savefig(OUT / "fig7_fix.png"); plt.close(fig)


def main():
    fig1_schematic()
    fig2_seed()
    fig3_population()
    fig4_belief()
    fig5_shock()
    fig6_external()
    fig7_fix()
    print("wrote 7 figures to", OUT)
    for p in sorted(OUT.glob("*.png")):
        print(" ", p.name, p.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
