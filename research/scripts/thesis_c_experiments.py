"""Thesis figures + tables for the c1 / c2 / c3 experiment suites.

Nature-style rendering matched to scripts/thesis_figures.py via the
shared scripts/_thesis_style.py preamble.

Figures (saved as PNG + SVG + PDF + 600dpi TIFF + sibling CSV):
  fig13_scale     — c1 closed-market scale sweep (n=10/20/50)
  fig14_tick      — c3 tick-horizon sweep (10/20/40 rounds)
  fig15_open      — c2 open-market preview price paths (SpaceX, 3 seeds)

Tables (CSV under docs/v13/tables/):
  table9_scale.csv      — c1 per-scale aggregated metrics
  table10_tick.csv      — c3 per-horizon aggregated metrics
  table11_open.csv      — c2 per-seed open-market preview metrics

Run:  uv run python scripts/thesis_c_experiments.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _thesis_style import (
    apply_style, finalize, fig_size, panel_label,
    BLUE, GREEN, RED, NEUTRAL_MID, NEUTRAL_DARK,
    COL_SINGLE_MM, COL_DOUBLE_MM,
)

apply_style()

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "docs" / "v13" / "figures"
TBL = ROOT / "docs" / "v13" / "tables"
FIG.mkdir(parents=True, exist_ok=True)
TBL.mkdir(parents=True, exist_ok=True)

# Roman Roy closed market settled NO; truth probability for YES = 0.
ROMAN_TRUTH = 0.0


def _runs(suite):
    idx = json.loads((ROOT / f"output/v13/{suite}/index.json").read_text())
    return {r["name"]: r["exp_id"] for r in idx["runs"]}


def _run_dir(suite, exp_id):
    return ROOT / f"output/v13/{suite}/{exp_id}"


def _run_metrics(suite, exp_id):
    """Per-run metrics from one experiment directory."""
    d = _run_dir(suite, exp_id)
    summary = json.loads((d / "analysis" / "summary.json").read_text())
    acts = pd.read_parquet(d / "raw" / "agent_actions.parquet")
    fills = pd.read_parquet(d / "raw" / "agent_fills.parquet")
    mids = (acts.dropna(subset=["yes_mid_after"])
            .groupby("tick_idx").yes_mid_after.last())
    pnl_min, pnl_max = summary["pnl_min"], summary["pnl_max"]
    return {
        "end_mid": float(mids.iloc[-1]),
        "start_mid": float(mids.iloc[0]),
        "volatility": float(mids.diff().std()),
        "n_actions": int(len(acts)),
        "n_fills": int(len(fills)),
        "notional": float(fills.notional.sum()),
        "cancel_pct": float((acts.action_type == "CANCEL").mean() * 100),
        "pnl_mean": float(summary["pnl_mean"]),
        "pnl_spread": float(pnl_max - pnl_min),
        "mids": mids,
    }


def _agg(rows, key):
    vals = np.array([r[key] for r in rows], dtype=float)
    return float(vals.mean()), float(vals.std())


# ----------------------------------------------------------------------
# Fig 13 — c1 closed-market scale sweep
# ----------------------------------------------------------------------
def fig_scale():
    runs = _runs("c1")
    scales = [10, 20, 50, 100]
    agg = {}
    for n in scales:
        rows = [_run_metrics("c1", runs[f"c1_closed_scale_n{n}_s{s}"])
                for s in (0, 1, 2)]
        agg[n] = rows

    fig, axes = plt.subplots(1, 3, figsize=fig_size(COL_DOUBLE_MM, 62))

    # Panel a — final YES price vs scale
    ax = axes[0]
    means = [_agg(agg[n], "end_mid")[0] for n in scales]
    sds = [_agg(agg[n], "end_mid")[1] for n in scales]
    x = np.arange(len(scales))
    ax.errorbar(x, means, yerr=sds, fmt="o-", color=BLUE, capsize=2.5,
                lw=1.0, label="simulated")
    for n_i, n in enumerate(scales):
        for r in agg[n]:
            ax.plot(n_i, r["end_mid"], "o", color=NEUTRAL_MID, ms=2.5,
                    alpha=0.7, zorder=1)
    ax.axhline(ROMAN_TRUTH, ls="--", lw=0.8, color=RED, label="truth (NO)")
    ax.set_xticks(x)
    ax.set_xticklabels([str(n) for n in scales])
    ax.set_xlabel("number of agents")
    ax.set_ylabel("final YES mid-price")
    ax.set_ylim(-0.03, 0.35)
    ax.legend(loc="upper right")
    panel_label(ax, "a")

    # Panel b — trading volume (notional) vs scale
    ax = axes[1]
    means = [_agg(agg[n], "notional")[0] for n in scales]
    sds = [_agg(agg[n], "notional")[1] for n in scales]
    ax.bar(x, means, yerr=sds, color=GREEN, width=0.55, capsize=2.5)
    ax.set_xticks(x)
    ax.set_xticklabels([str(n) for n in scales])
    ax.set_xlabel("number of agents")
    ax.set_ylabel("traded notional (USD)")
    panel_label(ax, "b")

    # Panel c — price volatility + cancel share vs scale
    ax = axes[2]
    vol_m = [_agg(agg[n], "volatility")[0] for n in scales]
    vol_s = [_agg(agg[n], "volatility")[1] for n in scales]
    ax.errorbar(x, vol_m, yerr=vol_s, fmt="s-", color=BLUE, capsize=2.5,
                lw=1.0, label="price volatility")
    ax.set_xticks(x)
    ax.set_xticklabels([str(n) for n in scales])
    ax.set_xlabel("number of agents")
    ax.set_ylabel("per-round price volatility")
    ax2 = ax.twinx()
    cancel_m = [_agg(agg[n], "cancel_pct")[0] for n in scales]
    ax2.plot(x, cancel_m, "^--", color=NEUTRAL_DARK, lw=1.0,
             label="cancel share")
    ax2.set_ylabel("cancel share (%)")
    ax2.set_ylim(0, 15)
    ax.spines["right"].set_visible(True)
    ax2.spines["top"].set_visible(False)
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [l.get_label() for l in lines], loc="upper left")
    panel_label(ax, "c")

    # source data
    src = []
    for n in scales:
        for s, r in zip((0, 1, 2), agg[n]):
            src.append({"n_agents": n, "seed": s, "end_mid": r["end_mid"],
                        "volatility": r["volatility"], "notional": r["notional"],
                        "n_fills": r["n_fills"], "cancel_pct": r["cancel_pct"],
                        "pnl_mean": r["pnl_mean"], "pnl_spread": r["pnl_spread"]})
    finalize(fig, FIG / "fig13_scale", source_data=pd.DataFrame(src))
    return agg


# ----------------------------------------------------------------------
# Fig 14 — c3 tick-horizon sweep
# ----------------------------------------------------------------------
def fig_tick():
    runs = _runs("c3")
    horizons = [10, 20, 50, 100]
    agg = {}
    for t in horizons:
        rows = [_run_metrics("c3", runs[f"c3_tick_horizon_t{t}_s{s}"])
                for s in (0, 1, 2)]
        agg[t] = rows

    fig, axes = plt.subplots(1, 3, figsize=fig_size(COL_DOUBLE_MM, 62))
    x = np.arange(len(horizons))

    # Panel a — final YES price vs horizon
    ax = axes[0]
    means = [_agg(agg[t], "end_mid")[0] for t in horizons]
    sds = [_agg(agg[t], "end_mid")[1] for t in horizons]
    ax.errorbar(x, means, yerr=sds, fmt="o-", color=BLUE, capsize=2.5,
                lw=1.0, label="simulated")
    for t_i, t in enumerate(horizons):
        for r in agg[t]:
            ax.plot(t_i, r["end_mid"], "o", color=NEUTRAL_MID, ms=2.5,
                    alpha=0.7, zorder=1)
    ax.axhline(ROMAN_TRUTH, ls="--", lw=0.8, color=RED, label="truth (NO)")
    ax.set_xticks(x)
    ax.set_xticklabels([str(t) for t in horizons])
    ax.set_xlabel("decision rounds")
    ax.set_ylabel("final YES mid-price")
    ax.set_ylim(-0.03, 0.35)
    ax.legend(loc="upper right")
    panel_label(ax, "a")

    # Panel b — cumulative actions vs horizon
    ax = axes[1]
    means = [_agg(agg[t], "n_actions")[0] for t in horizons]
    sds = [_agg(agg[t], "n_actions")[1] for t in horizons]
    ax.bar(x, means, yerr=sds, color=GREEN, width=0.55, capsize=2.5)
    ax.set_xticks(x)
    ax.set_xticklabels([str(t) for t in horizons])
    ax.set_xlabel("decision rounds")
    ax.set_ylabel("total agent actions")
    panel_label(ax, "b")

    # Panel c — mean price path by horizon (seed-averaged)
    ax = axes[2]
    colors = {10: BLUE, 20: GREEN, 50: NEUTRAL_DARK, 100: RED}
    for t in horizons:
        # align by fraction of horizon completed
        paths = []
        for r in agg[t]:
            m = r["mids"].to_numpy()
            paths.append(m)
        L = min(len(p) for p in paths)
        arr = np.array([p[:L] for p in paths])
        mean_path = arr.mean(axis=0)
        frac = np.linspace(0, 1, L)
        ax.plot(frac, mean_path, "-", color=colors[t], lw=1.1,
                label=f"{t} rounds")
    ax.axhline(ROMAN_TRUTH, ls="--", lw=0.8, color=RED)
    ax.set_xlabel("fraction of horizon")
    ax.set_ylabel("YES mid-price")
    ax.set_ylim(-0.03, 0.35)
    ax.legend(loc="upper right")
    panel_label(ax, "c")

    src = []
    for t in horizons:
        for s, r in zip((0, 1, 2), agg[t]):
            src.append({"n_ticks": t, "seed": s, "end_mid": r["end_mid"],
                        "volatility": r["volatility"], "n_actions": r["n_actions"],
                        "n_fills": r["n_fills"], "pnl_mean": r["pnl_mean"],
                        "pnl_spread": r["pnl_spread"]})
    finalize(fig, FIG / "fig14_tick", source_data=pd.DataFrame(src))
    return agg


# ----------------------------------------------------------------------
# Fig 15 — c2 open-market preview price paths
# ----------------------------------------------------------------------
def fig_open():
    runs = _runs("c2")
    rows = {s: _run_metrics("c2", runs[f"c2_open_preview_spacex_n20_s{s}"])
            for s in (0, 1, 2)}

    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM + 20, 65))
    colors = {0: BLUE, 1: GREEN, 2: NEUTRAL_DARK}
    src = []
    for s in (0, 1, 2):
        m = rows[s]["mids"]
        ax.plot(m.index, m.to_numpy(), "-", color=colors[s], lw=1.0,
                label=f"seed {s}")
        for tick, val in m.items():
            src.append({"seed": s, "tick": int(tick), "yes_mid": float(val)})
    start = np.mean([rows[s]["start_mid"] for s in (0, 1, 2)])
    ax.axhline(start, ls=":", lw=0.8, color=NEUTRAL_MID,
               label="market open")
    ax.set_xlabel("decision round")
    ax.set_ylabel("YES mid-price")
    ax.set_ylim(0.55, 0.80)
    ax.legend(loc="lower right")
    finalize(fig, FIG / "fig15_open", source_data=pd.DataFrame(src))
    return rows


# ----------------------------------------------------------------------
# Fig 16 — c4 profile-distribution sweep
# ----------------------------------------------------------------------
PROFILE_LABEL = {
    "Archetype-C0": "diffuse",
    "Archetype-C1": "one-shot",
    "Archetype-C2": "longshot",
    "Archetype-C3": "contrarian",
}
PROFILE_ORDER = ["Archetype-C0", "Archetype-C1",
                 "Archetype-C2", "Archetype-C3"]
VARIANTS = ["natural", "uniform", "concentrated"]


def _profile_counts(suite, exp_id):
    """Realized count of each behaviour profile in one run."""
    d = _run_dir(suite, exp_id)
    per = pd.read_parquet(d / "raw" / "agent_personas.parquet")
    vc = per["persona_type"].value_counts()
    return {p: int(vc.get(p, 0)) for p in PROFILE_ORDER}


def fig_profile_mix():
    runs = _runs("c4")
    agg = {}
    counts = {}
    for v in VARIANTS:
        rows, cnt = [], []
        for s in (0, 1, 2):
            eid = runs[f"c4_profile_mix_{v}_s{s}"]
            rows.append(_run_metrics("c4", eid))
            cnt.append(_profile_counts("c4", eid))
        agg[v] = rows
        counts[v] = cnt

    fig, axes = plt.subplots(1, 3, figsize=fig_size(COL_DOUBLE_MM, 62))
    x = np.arange(len(VARIANTS))
    vlabel = ["natural", "uniform", "longshot-\nheavy"]

    # Panel a — final YES price by profile mix
    ax = axes[0]
    means = [_agg(agg[v], "end_mid")[0] for v in VARIANTS]
    sds = [_agg(agg[v], "end_mid")[1] for v in VARIANTS]
    ax.errorbar(x, means, yerr=sds, fmt="o-", color=BLUE, capsize=2.5,
                lw=1.0, label="simulated")
    for v_i, v in enumerate(VARIANTS):
        for r in agg[v]:
            ax.plot(v_i, r["end_mid"], "o", color=NEUTRAL_MID, ms=2.5,
                    alpha=0.7, zorder=1)
    ax.axhline(ROMAN_TRUTH, ls="--", lw=0.8, color=RED, label="truth (NO)")
    ax.set_xticks(x)
    ax.set_xticklabels(vlabel)
    ax.set_xlabel("profile mix")
    ax.set_ylabel("final YES mid-price")
    ax.set_ylim(-0.03, 0.35)
    ax.legend(loc="upper right")
    panel_label(ax, "a")

    # Panel b — volatility + traded notional by profile mix
    ax = axes[1]
    vol_m = [_agg(agg[v], "volatility")[0] for v in VARIANTS]
    vol_s = [_agg(agg[v], "volatility")[1] for v in VARIANTS]
    ax.errorbar(x, vol_m, yerr=vol_s, fmt="s-", color=BLUE, capsize=2.5,
                lw=1.0, label="price volatility")
    ax.set_xticks(x)
    ax.set_xticklabels(vlabel)
    ax.set_xlabel("profile mix")
    ax.set_ylabel("per-round price volatility")
    ax2 = ax.twinx()
    notion_m = [_agg(agg[v], "notional")[0] for v in VARIANTS]
    ax2.plot(x, notion_m, "^--", color=NEUTRAL_DARK, lw=1.0,
             label="traded notional")
    ax2.set_ylabel("traded notional (USD)")
    ax.spines["right"].set_visible(True)
    ax2.spines["top"].set_visible(False)
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [l.get_label() for l in lines], loc="upper left")
    panel_label(ax, "b")

    # Panel c — realized profile composition (seed-summed) by mix
    ax = axes[2]
    pcolors = {"Archetype-C0": BLUE, "Archetype-C1": GREEN,
               "Archetype-C2": RED, "Archetype-C3": NEUTRAL_DARK}
    bottom = np.zeros(len(VARIANTS))
    for p in PROFILE_ORDER:
        vals = []
        for v in VARIANTS:
            tot = sum(sum(c.values()) for c in counts[v])
            share = sum(c[p] for c in counts[v]) / tot * 100
            vals.append(share)
        ax.bar(x, vals, bottom=bottom, width=0.6, color=pcolors[p],
               label=PROFILE_LABEL[p])
        bottom += np.array(vals)
    ax.set_xticks(x)
    ax.set_xticklabels(vlabel)
    ax.set_xlabel("profile mix")
    ax.set_ylabel("realized profile share (%)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=2,
              fontsize=6.0)
    panel_label(ax, "c")

    src = []
    for v in VARIANTS:
        for s, r, c in zip((0, 1, 2), agg[v], counts[v]):
            row = {"variant": v, "seed": s, "end_mid": r["end_mid"],
                   "volatility": r["volatility"], "notional": r["notional"],
                   "n_fills": r["n_fills"], "pnl_mean": r["pnl_mean"],
                   "pnl_spread": r["pnl_spread"]}
            row.update({PROFILE_LABEL[p]: c[p] for p in PROFILE_ORDER})
            src.append(row)
    finalize(fig, FIG / "fig16_profile_mix", source_data=pd.DataFrame(src))
    return agg, counts


# ----------------------------------------------------------------------
# Fig 17 — c5 thinking-mode comparison
# ----------------------------------------------------------------------
ACTION_TYPES = ["LIMIT", "MARKET", "CANCEL", "HOLD", "SPLIT",
                "MERGE", "UPDATE_BELIEF"]
ACTION_EN = {"LIMIT": "limit", "MARKET": "market", "CANCEL": "cancel",
             "HOLD": "hold", "SPLIT": "split", "MERGE": "merge",
             "UPDATE_BELIEF": "belief"}
THINK_MODES = ["on", "off"]


def _action_mix(suite, exp_id):
    """Action-type share (%) for one run."""
    d = _run_dir(suite, exp_id)
    acts = pd.read_parquet(d / "raw" / "agent_actions.parquet")
    vc = acts["action_type"].value_counts(normalize=True) * 100
    return {a: float(vc.get(a, 0.0)) for a in ACTION_TYPES}


def fig_thinking():
    runs = _runs("c5")
    agg, mixes = {}, {}
    for m in THINK_MODES:
        rows, mx = [], []
        for s in (0, 1, 2):
            eid = runs[f"c5_thinking_{m}_s{s}"]
            rows.append(_run_metrics("c5", eid))
            mx.append(_action_mix("c5", eid))
        agg[m] = rows
        mixes[m] = mx

    fig, axes = plt.subplots(1, 3, figsize=fig_size(COL_DOUBLE_MM, 62))
    x = np.arange(len(THINK_MODES))
    mlabel = ["thinking\non", "thinking\noff"]

    # Panel a — final YES price by thinking mode
    ax = axes[0]
    means = [_agg(agg[m], "end_mid")[0] for m in THINK_MODES]
    sds = [_agg(agg[m], "end_mid")[1] for m in THINK_MODES]
    ax.errorbar(x, means, yerr=sds, fmt="o-", color=BLUE, capsize=2.5,
                lw=1.0, label="simulated")
    for m_i, m in enumerate(THINK_MODES):
        for r in agg[m]:
            ax.plot(m_i, r["end_mid"], "o", color=NEUTRAL_MID, ms=2.5,
                    alpha=0.7, zorder=1)
    ax.axhline(ROMAN_TRUTH, ls="--", lw=0.8, color=RED, label="truth (NO)")
    ax.set_xticks(x)
    ax.set_xticklabels(mlabel)
    ax.set_xlabel("reasoning mode")
    ax.set_ylabel("final YES mid-price")
    ax.set_ylim(-0.03, 0.35)
    ax.legend(loc="upper right")
    panel_label(ax, "a")

    # Panel b — volatility + traded notional by thinking mode
    ax = axes[1]
    vol_m = [_agg(agg[m], "volatility")[0] for m in THINK_MODES]
    vol_s = [_agg(agg[m], "volatility")[1] for m in THINK_MODES]
    ax.errorbar(x, vol_m, yerr=vol_s, fmt="s-", color=BLUE, capsize=2.5,
                lw=1.0, label="price volatility")
    ax.set_xticks(x)
    ax.set_xticklabels(mlabel)
    ax.set_xlabel("reasoning mode")
    ax.set_ylabel("per-round price volatility")
    ax2 = ax.twinx()
    notion_m = [_agg(agg[m], "notional")[0] for m in THINK_MODES]
    ax2.plot(x, notion_m, "^--", color=NEUTRAL_DARK, lw=1.0,
             label="traded notional")
    ax2.set_ylabel("traded notional (USD)")
    ax.spines["right"].set_visible(True)
    ax2.spines["top"].set_visible(False)
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [l.get_label() for l in lines], loc="upper left")
    panel_label(ax, "b")

    # Panel c — action mix, thinking on vs off
    ax = axes[2]
    width = 0.38
    ax_x = np.arange(len(ACTION_TYPES))
    for i, m in enumerate(THINK_MODES):
        vals = [np.mean([mx[a] for mx in mixes[m]]) for a in ACTION_TYPES]
        ax.bar(ax_x + (i - 0.5) * width, vals, width,
               color=(BLUE if m == "on" else NEUTRAL_DARK),
               label=f"thinking {m}")
    ax.set_xticks(ax_x)
    ax.set_xticklabels([ACTION_EN[a] for a in ACTION_TYPES],
                       rotation=45, ha="right", fontsize=6.0)
    ax.set_ylabel("action share (%)")
    ax.legend(loc="upper right")
    panel_label(ax, "c")

    src = []
    for m in THINK_MODES:
        for s, r, mx in zip((0, 1, 2), agg[m], mixes[m]):
            row = {"thinking": m, "seed": s, "end_mid": r["end_mid"],
                   "volatility": r["volatility"], "notional": r["notional"],
                   "n_fills": r["n_fills"], "pnl_mean": r["pnl_mean"],
                   "pnl_spread": r["pnl_spread"]}
            row.update({ACTION_EN[a]: mx[a] for a in ACTION_TYPES})
            src.append(row)
    finalize(fig, FIG / "fig17_thinking", source_data=pd.DataFrame(src))
    return agg, mixes


# ----------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------
def table_scale(agg):
    horizons = [10, 20, 50, 100]
    rows = []
    for n in horizons:
        em, es = _agg(agg[n], "end_mid")
        vm, _ = _agg(agg[n], "volatility")
        nm, _ = _agg(agg[n], "notional")
        fm, _ = _agg(agg[n], "n_fills")
        cm, _ = _agg(agg[n], "cancel_pct")
        sm, _ = _agg(agg[n], "pnl_spread")
        rows.append({
            "n_agents": n,
            "end_mid_mean": round(em, 3),
            "end_mid_sd": round(es, 3),
            "volatility": round(vm, 4),
            "notional_mean": round(nm, 0),
            "fills_mean": round(fm, 1),
            "cancel_pct": round(cm, 1),
            "pnl_spread_mean": round(sm, 0),
        })
    pd.DataFrame(rows).to_csv(TBL / "table9_scale.csv", index=False)


def table_tick(agg):
    horizons = [10, 20, 50, 100]
    rows = []
    for t in horizons:
        em, es = _agg(agg[t], "end_mid")
        vm, _ = _agg(agg[t], "volatility")
        am, _ = _agg(agg[t], "n_actions")
        fm, _ = _agg(agg[t], "n_fills")
        sm, _ = _agg(agg[t], "pnl_spread")
        rows.append({
            "n_ticks": t,
            "end_mid_mean": round(em, 3),
            "end_mid_sd": round(es, 3),
            "volatility": round(vm, 4),
            "actions_mean": round(am, 0),
            "fills_mean": round(fm, 1),
            "pnl_spread_mean": round(sm, 0),
        })
    pd.DataFrame(rows).to_csv(TBL / "table10_tick.csv", index=False)


def table_open(rows):
    out = []
    for s in (0, 1, 2):
        r = rows[s]
        out.append({
            "seed": s,
            "start_mid": round(r["start_mid"], 3),
            "end_mid": round(r["end_mid"], 3),
            "drift": round(r["end_mid"] - r["start_mid"], 3),
            "volatility": round(r["volatility"], 4),
            "n_fills": r["n_fills"],
            "pnl_mean": round(r["pnl_mean"], 2),
        })
    pd.DataFrame(out).to_csv(TBL / "table11_open.csv", index=False)


def table_profile_mix(agg, counts):
    name = {"natural": "自然分布", "uniform": "均匀分布",
            "concentrated": "高赔率主导"}
    rows = []
    for v in VARIANTS:
        em, es = _agg(agg[v], "end_mid")
        vm, _ = _agg(agg[v], "volatility")
        nm, _ = _agg(agg[v], "notional")
        fm, _ = _agg(agg[v], "n_fills")
        sm, _ = _agg(agg[v], "pnl_spread")
        # realized longshot (C2) share across the 3 seeds
        tot = sum(sum(c.values()) for c in counts[v])
        c2 = sum(c["Archetype-C2"] for c in counts[v]) / tot * 100
        rows.append({
            "variant": name[v],
            "end_mid_mean": round(em, 3),
            "end_mid_sd": round(es, 3),
            "volatility": round(vm, 4),
            "notional_mean": round(nm, 0),
            "fills_mean": round(fm, 1),
            "longshot_share_pct": round(c2, 1),
            "pnl_spread_mean": round(sm, 0),
        })
    pd.DataFrame(rows).to_csv(TBL / "table12_profile_mix.csv", index=False)


def table_thinking(agg):
    name = {"on": "思考开", "off": "思考关"}
    rows = []
    for m in THINK_MODES:
        em, es = _agg(agg[m], "end_mid")
        vm, _ = _agg(agg[m], "volatility")
        nm, _ = _agg(agg[m], "notional")
        fm, _ = _agg(agg[m], "n_fills")
        sm, _ = _agg(agg[m], "pnl_spread")
        rows.append({
            "mode": name[m],
            "end_mid_mean": round(em, 3),
            "end_mid_sd": round(es, 3),
            "volatility": round(vm, 4),
            "notional_mean": round(nm, 0),
            "fills_mean": round(fm, 1),
            "pnl_spread_mean": round(sm, 0),
        })
    pd.DataFrame(rows).to_csv(TBL / "table13_thinking.csv", index=False)


def main():
    scale_agg = fig_scale()
    tick_agg = fig_tick()
    open_rows = fig_open()
    table_scale(scale_agg)
    table_tick(tick_agg)
    table_open(open_rows)
    try:
        mix_agg, mix_counts = fig_profile_mix()
        table_profile_mix(mix_agg, mix_counts)
    except (FileNotFoundError, KeyError) as exc:
        print(f"skipped c4 profile-mix figures (suite not ready): {exc}")
    try:
        think_agg, _ = fig_thinking()
        table_thinking(think_agg)
    except (FileNotFoundError, KeyError) as exc:
        print(f"skipped c5 thinking figures (suite not ready): {exc}")
    print("figures + tables written to docs/v13/figures/ and docs/v13/tables/")


if __name__ == "__main__":
    main()
