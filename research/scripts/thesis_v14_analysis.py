"""v14 aggregate analysis + figures, organized by the 5 research questions.

Inputs:  output/v14/<suite>/<exp_id>/{raw,analysis}/...
Outputs: docs/v14/figures/  +  docs/v14/tables/

RQ1  rq1 panel (10 markets × 3 seeds): can agents reproduce real trader
     behaviour on closed markets?
RQ2  c1 scale (n=10/20/50/100 × 2 base markets): how does agent count
     affect simulated behaviour?
RQ3  c3 tick (t=10/20/50/100 × 2 base markets): how does horizon affect
     simulated behaviour?
RQ4  c4 profile-mix (natural/uniform/concentrated × 2 base markets) and
     c5 thinking-mode (on/off × 2 base markets): which design choices
     matter?
RQ5  rq5 (Thunder NBA Finals, 3 seeds): can the tool produce pre-close
     evidence on an open market?

Output filenames use readable Chinese semantic names so the figure and
table folders can be inspected without decoding internal experiment IDs.

Run:   uv run python scripts/thesis_v14_analysis.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _thesis_labels import (
    LEGEND_FINAL_PRICE, LEGEND_MARKET_OPEN, LEGEND_TRUTH, LEGEND_TRUTH_NO,
    LEGEND_TRUTH_YES, PROFILE_VARIANT, XLABEL_DECISION_ROUND, XLABEL_HORIZON_FRAC,
    XLABEL_N_AGENTS, XLABEL_PROFILE_MIX, XLABEL_SEEDS_TOWARD_TRUTH,
    XLABEL_YES_MID, XLABEL_YES_MID_PATH, XLABEL_YES_MID_SEED_AVG,
    XLABEL_ACTION_SHARE, YLABEL_END_MID, YLABEL_NOTIONAL, YLABEL_PNL_SPREAD,
    market_title, rounds_label, seed_label, thinking_label,
)
from _thesis_style import (
    apply_style, finalize, fig_size, fig_size_vstack, panel_label,
    BLUE, GREEN, RED, TEAL, VIOLET, NEUTRAL_LIGHT, NEUTRAL_MID, NEUTRAL_DARK,
    COL_SINGLE_MM, COL_DOUBLE_MM,
)

MKT_LINE = {"robotaxi": BLUE, "ethereum": TEAL}

apply_style()

ROOT = Path(__file__).resolve().parent.parent
OUT_FIG = ROOT / "docs" / "v14" / "figures"
OUT_TBL = ROOT / "docs" / "v14" / "tables"
OUT_FIG.mkdir(parents=True, exist_ok=True)
OUT_TBL.mkdir(parents=True, exist_ok=True)

V14 = ROOT / "output" / "v14"

FIG_RQ1_PANEL = "行为可信性_跨市场价格路径与真值移动"
FIG_RQ2_SCALE = "规模效应_智能体数量对价格成交和盈亏分化的影响"
FIG_RQ3_TICK = "时长效应_模拟轮数对价格路径和路径依赖的影响"
FIG_RQ4_PROFILE = "模块消融_画像分布对市场结果的影响"
FIG_RQ4_THINKING = "模块消融_思考模式对动作结构的影响"
FIG_RQ5_OPEN = "开放市场_结算前情景价格路径"

TBL_RQ1_PANEL = "表_行为可信性_跨市场价格路径与真值移动.csv"
TBL_RQ2_SCALE = "表_规模效应_智能体数量核心指标.csv"
TBL_RQ3_TICK = "表_时长效应_模拟轮数核心指标.csv"
TBL_RQ4_PROFILE = "表_模块消融_画像分布核心指标.csv"
TBL_RQ4_THINKING = "表_模块消融_思考模式核心指标.csv"
TBL_RQ5_OPEN = "表_开放市场_结算前情景指标.csv"


# ──────────────────────────────────────────────────────────────────────
# data access helpers
# ──────────────────────────────────────────────────────────────────────
def runs_of(suite: str) -> list[Path]:
    return sorted((V14 / suite).glob("2026*/"))


def config_name(run: Path) -> str:
    """Extract <config-name> from `<ts>-<config-name>-<git>-<cfghash>`."""
    parts = run.name.split("-")
    return "-".join(parts[1:-2])


def metrics(run: Path) -> dict:
    """Standard per-run metrics from raw + analysis."""
    summ = json.loads((run / "analysis" / "summary.json").read_text())
    meta = json.loads((run / "meta.json").read_text())
    acts = pd.read_parquet(run / "raw" / "agent_actions.parquet")
    fills = pd.read_parquet(run / "raw" / "agent_fills.parquet")
    mids = (acts.dropna(subset=["yes_mid_after"])
            .groupby("tick_idx").yes_mid_after.last())
    mix = (acts["action_type"].value_counts(normalize=True) * 100).to_dict()
    return {
        "config": config_name(run),
        "n_agents": summ["n_agents"],
        "n_ticks": summ["n_ticks"],
        "signal_mu": meta["priors_summary"]["signal_mu"],
        "start_mid": float(mids.iloc[0]),
        "end_mid": float(mids.iloc[-1]),
        "volatility": float(mids.diff().std()),
        "n_actions": int(len(acts)),
        "n_fills": int(len(fills)),
        "notional": float(fills["notional"].sum()),
        "cancel_pct": mix.get("CANCEL", 0.0),
        "pnl_mean": summ["pnl_mean"],
        "pnl_spread": summ["pnl_max"] - summ["pnl_min"],
        "mids": mids,
        "action_mix": mix,
        "slug": meta["config"]["market"]["slug"],
    }


def truth_yes(slug: str) -> float:
    """Real outcome as YES probability (1.0 or 0.0)."""
    p = ROOT / f"data/priors_{slug}.json"
    if not p.exists():
        return float("nan")
    d = json.loads(p.read_text())
    wi = d.get("winning_idx")
    if wi is None or wi < 0:
        return float("nan")
    return 1.0 if wi == 0 else 0.0


# ──────────────────────────────────────────────────────────────────────
# RQ1 — cross-market panel (10 markets × 3 seeds)
# ──────────────────────────────────────────────────────────────────────
def fig_rq1():
    rows = [metrics(r) for r in runs_of("rq1")]
    by_market: dict[str, list[dict]] = {}
    for r in rows:
        by_market.setdefault(r["slug"], []).append(r)

    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2))

    # Panel a — normalized price trajectories per market
    ax = axes[0]
    src = []
    for slug, runs_ in by_market.items():
        truth = truth_yes(slug)
        # seed-averaged path normalised by length
        L = min(len(r["mids"]) for r in runs_)
        arr = np.array([r["mids"].to_numpy()[:L] for r in runs_])
        mean_path = arr.mean(axis=0)
        frac = np.linspace(0, 1, L)
        color = GREEN if truth == 1.0 else (RED if truth == 0.0 else NEUTRAL_MID)
        ax.plot(frac, mean_path, "-", lw=0.9, color=color, alpha=0.7)
        for t, v in zip(frac, mean_path):
            src.append({"slug": slug, "truth": truth,
                        "frac": float(t), "yes_mid": float(v)})
    ax.set_xlabel(XLABEL_HORIZON_FRAC)
    ax.set_ylabel(XLABEL_YES_MID_SEED_AVG)
    ax.set_ylim(-0.03, 1.03)
    # legend explainer
    ax.plot([], [], "-", color=GREEN, label=LEGEND_TRUTH_YES)
    ax.plot([], [], "-", color=RED, label=LEGEND_TRUTH_NO)
    ax.legend(loc="upper right")
    panel_label(ax, "a")

    # Panel b — direction-toward-truth per market
    ax = axes[1]
    market_short = {}
    for slug, runs_ in by_market.items():
        truth = truth_yes(slug)
        # is end_mid moved toward truth from start?
        dirs = []
        for r in runs_:
            if np.isnan(truth):
                continue
            delta = r["end_mid"] - r["start_mid"]
            move = (delta > 0 and truth == 1.0) or (delta < 0 and truth == 0.0)
            dirs.append(1 if move else 0)
        market_short[slug] = (sum(dirs), len(dirs), truth)
    # sort by truth then by hit rate
    ordered = sorted(market_short.items(),
                     key=lambda kv: (kv[1][2], kv[1][0] / max(kv[1][1], 1)))
    y = np.arange(len(ordered))
    hit_pct = [(v[0] / v[1]) * 100 if v[1] else 0 for _, v in ordered]
    colors = [GREEN if v[2] == 1.0 else RED for _, v in ordered]
    ax.barh(y, hit_pct, color=colors, edgecolor=NEUTRAL_DARK, linewidth=0.6)
    short = [s[:22] + "…" if len(s) > 22 else s for s, _ in ordered]
    ax.set_yticks(y)
    ax.set_yticklabels(short, fontsize=6.0)
    ax.set_xlabel(XLABEL_SEEDS_TOWARD_TRUTH)
    ax.axvline(50, ls=":", lw=0.6, color=NEUTRAL_MID)
    panel_label(ax, "b")

    finalize(fig, OUT_FIG / FIG_RQ1_PANEL, source_data=pd.DataFrame(src))

    # table 1: per-market metrics
    tbl = []
    for slug, runs_ in by_market.items():
        truth = truth_yes(slug)
        ends = [r["end_mid"] for r in runs_]
        starts = [r["start_mid"] for r in runs_]
        moves = sum(1 for r in runs_
                    if (r["end_mid"] - r["start_mid"]) *
                        ((1 if truth == 1.0 else -1) if not np.isnan(truth) else 0) > 0)
        tbl.append({
            "market": slug, "truth": truth,
            "start_mid": round(np.mean(starts), 3),
            "end_mid_mean": round(np.mean(ends), 3),
            "end_mid_sd": round(np.std(ends, ddof=1), 3),
            "n_seeds_toward_truth": moves,
            "n_seeds": len(runs_),
        })
    pd.DataFrame(tbl).to_csv(OUT_TBL / TBL_RQ1_PANEL, index=False)


# ──────────────────────────────────────────────────────────────────────
# RQ2 — scale (c1, two base markets)
# ──────────────────────────────────────────────────────────────────────
def _grouped(suite, key_re):
    """Group runs by the regex-captured key from config name."""
    out: dict = {}
    for r in runs_of(suite):
        m = re.search(key_re, config_name(r))
        if not m:
            continue
        out.setdefault(m.group(1), []).append(metrics(r))
    return out


def _agg(rows, k):
    v = np.array([r[k] for r in rows], dtype=float)
    return v.mean(), v.std(ddof=1) if len(v) > 1 else 0.0


def _bipanel_x_metric(grouped_by_market, xs, metric_key, ylabel, truth_dict):
    """A 2×1 figure: each panel a base market; x-axis = sweep variable."""
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=55))
    src = []
    for ax, (mkt, grouped) in zip(axes, grouped_by_market.items()):
        means = [_agg(grouped[str(x)], metric_key)[0] for x in xs]
        sds = [_agg(grouped[str(x)], metric_key)[1] for x in xs]
        xi = np.arange(len(xs))
        ax.errorbar(xi, means, yerr=sds, fmt="o-", color=BLUE, capsize=2.5,
                    lw=1.0)
        for i, x in enumerate(xs):
            for r in grouped[str(x)]:
                ax.plot(i, r[metric_key], "o", color=NEUTRAL_MID, ms=2.5,
                        alpha=0.6, zorder=1)
                src.append({"base": mkt, "x": x, "seed_value": r[metric_key]})
        truth = truth_dict.get(mkt)
        if truth is not None and metric_key == "end_mid":
            ax.axhline(truth, ls="--", lw=0.8, color=RED,
                       label=f"{LEGEND_TRUTH} ({'YES' if truth == 1.0 else 'NO'})")
            ax.legend(loc="best", fontsize=6.0)
        ax.set_xticks(xi); ax.set_xticklabels([str(x) for x in xs])
        ax.set_xlabel("")
        ax.set_ylabel(ylabel)
        ax.set_title(market_title(mkt), fontsize=7, color=NEUTRAL_DARK)
    return fig, src


def fig_rq2():
    ns = [10, 20, 50, 100]
    # one row per metric — make a single multi-panel figure
    by_mkt = {}
    for mkt in ("robotaxi", "ethereum"):
        g = _grouped(f"c1_{mkt}", r"_n(\d+)_")
        by_mkt[mkt] = g
    truth = {"robotaxi": truth_yes(metrics(runs_of("c1_robotaxi")[0])["slug"]),
             "ethereum": truth_yes(metrics(runs_of("c1_ethereum")[0])["slug"])}

    fig, axes = plt.subplots(3, 1, figsize=fig_size_vstack(3, panel_mm=55))
    metric_specs = [
        ("end_mid", YLABEL_END_MID, "a"),
        ("notional", YLABEL_NOTIONAL, "b"),
        ("pnl_spread", YLABEL_PNL_SPREAD, "c"),
    ]
    src = []
    for row, (k, ylab, lbl) in enumerate(metric_specs):
        ax = axes[row]
        for mkt, grouped in by_mkt.items():
            means = [_agg(grouped[str(n)], k)[0] for n in ns]
            sds = [_agg(grouped[str(n)], k)[1] for n in ns]
            xi = np.arange(len(ns))
            color = MKT_LINE[mkt]
            ax.errorbar(xi, means, yerr=sds, fmt="o-", color=color,
                        capsize=2.5, lw=1.0, label=market_title(mkt))
            for i, n in enumerate(ns):
                for r in grouped[str(n)]:
                    ax.plot(i, r[k], "o", color=NEUTRAL_MID, ms=2.5,
                            alpha=0.6, zorder=1)
                    src.append({"base": mkt, "metric": k, "n": n,
                                "seed_value": r[k]})
            if k == "end_mid":
                ax.axhline(truth[mkt], ls=":", lw=0.7, color=color, alpha=0.5)
        if k == "end_mid":
            ax.set_ylim(-0.03, 1.03)
        ax.set_xticks(xi); ax.set_xticklabels([str(n) for n in ns])
        if row == 2:
            ax.set_xlabel(XLABEL_N_AGENTS)
        ax.set_ylabel(ylab)
        ax.legend(loc="best", fontsize=6.0)
        panel_label(ax, lbl)
    finalize(fig, OUT_FIG / FIG_RQ2_SCALE, source_data=pd.DataFrame(src))

    # table
    rows = []
    for mkt, grouped in by_mkt.items():
        for n in ns:
            em, es = _agg(grouped[str(n)], "end_mid")
            v, _ = _agg(grouped[str(n)], "volatility")
            no, _ = _agg(grouped[str(n)], "notional")
            f, _ = _agg(grouped[str(n)], "n_fills")
            ca, _ = _agg(grouped[str(n)], "cancel_pct")
            ps, _ = _agg(grouped[str(n)], "pnl_spread")
            rows.append({"base": mkt, "n_agents": n,
                         "end_mid_mean": round(em, 3),
                         "end_mid_sd": round(es, 3),
                         "volatility": round(v, 4),
                         "notional_mean": round(no, 0),
                         "fills_mean": round(f, 1),
                         "cancel_pct": round(ca, 1),
                         "pnl_spread_mean": round(ps, 0)})
    pd.DataFrame(rows).to_csv(OUT_TBL / TBL_RQ2_SCALE, index=False)


# ──────────────────────────────────────────────────────────────────────
# RQ3 — tick horizon (c3, two base markets)
# ──────────────────────────────────────────────────────────────────────
def fig_rq3():
    ts = [10, 20, 50, 100]
    by_mkt = {mkt: _grouped(f"c3_{mkt}", r"_t(\d+)_") for mkt in ("robotaxi", "ethereum")}
    truth = {"robotaxi": truth_yes(metrics(runs_of("c1_robotaxi")[0])["slug"]),
             "ethereum": truth_yes(metrics(runs_of("c1_ethereum")[0])["slug"])}

    fig, axes = plt.subplots(4, 1, figsize=fig_size_vstack(4, panel_mm=52))
    src = []
    colors_t = {10: BLUE, 20: GREEN, 50: NEUTRAL_DARK, 100: RED}
    for idx, (mkt, grouped) in enumerate(by_mkt.items()):
        ax_end = axes[idx]
        em = [_agg(grouped[str(t)], "end_mid")[0] for t in ts]
        es = [_agg(grouped[str(t)], "end_mid")[1] for t in ts]
        xi = np.arange(len(ts))
        ax_end.errorbar(xi, em, yerr=es, fmt="o-", color=MKT_LINE[mkt],
                        capsize=2.5, lw=1.0)
        ax_end.axhline(truth[mkt], ls="--", lw=0.8, color=MKT_LINE[mkt])
        ax_end.set_ylim(-0.03, 1.03)
        ax_end.set_xticks(xi); ax_end.set_xticklabels([str(t) for t in ts])
        ax_end.set_ylabel(YLABEL_END_MID)
        ax_end.set_title(market_title(mkt), fontsize=7, color=NEUTRAL_DARK)
        if idx == 0:
            panel_label(ax_end, "a")

        ax_path = axes[idx + 2]
        for t in ts:
            rows = grouped[str(t)]
            L = min(len(r["mids"]) for r in rows)
            arr = np.array([r["mids"].to_numpy()[:L] for r in rows])
            ax_path.plot(np.linspace(0, 1, L), arr.mean(axis=0), "-",
                         color=colors_t[t], lw=1.0, label=rounds_label(t))
            for t_i, v in zip(np.linspace(0, 1, L), arr.mean(axis=0)):
                src.append({"base": mkt, "rounds": t, "frac": float(t_i),
                            "yes_mid": float(v)})
        ax_path.axhline(truth[mkt], ls="--", lw=0.8, color=MKT_LINE[mkt])
        ax_path.set_xlabel(XLABEL_HORIZON_FRAC)
        ax_path.set_ylabel(XLABEL_YES_MID_PATH)
        ax_path.set_ylim(-0.03, 1.03)
        ax_path.set_title(market_title(mkt), fontsize=7, color=NEUTRAL_DARK)
        ax_path.legend(loc="best", fontsize=6.0)
        if idx == 0:
            panel_label(ax_path, "b")
    finalize(fig, OUT_FIG / FIG_RQ3_TICK, source_data=pd.DataFrame(src))

    # table
    rows = []
    for mkt, grouped in by_mkt.items():
        for t in ts:
            em, es = _agg(grouped[str(t)], "end_mid")
            v, _ = _agg(grouped[str(t)], "volatility")
            a, _ = _agg(grouped[str(t)], "n_actions")
            f, _ = _agg(grouped[str(t)], "n_fills")
            rows.append({"base": mkt, "n_ticks": t,
                         "end_mid_mean": round(em, 3),
                         "end_mid_sd": round(es, 3),
                         "volatility": round(v, 4),
                         "actions_mean": round(a, 0),
                         "fills_mean": round(f, 1)})
    pd.DataFrame(rows).to_csv(OUT_TBL / TBL_RQ3_TICK, index=False)


# ──────────────────────────────────────────────────────────────────────
# RQ4 — profile mix (c4) + thinking mode (c5)
# ──────────────────────────────────────────────────────────────────────
def fig_rq4_profile():
    variants = ["natural", "uniform", "concentrated"]
    by_mkt = {mkt: _grouped(f"c4_{mkt}",
                            r"_(natural|uniform|concentrated)_")
              for mkt in ("robotaxi", "ethereum")}
    truth = {"robotaxi": truth_yes(metrics(runs_of("c1_robotaxi")[0])["slug"]),
             "ethereum": truth_yes(metrics(runs_of("c1_ethereum")[0])["slug"])}

    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=52))
    src = []
    for ax, (mkt, grouped) in zip(axes, by_mkt.items()):
        em = [_agg(grouped[v], "end_mid")[0] for v in variants]
        es = [_agg(grouped[v], "end_mid")[1] for v in variants]
        xi = np.arange(len(variants))
        ax.errorbar(xi, em, yerr=es, fmt="o-", color=BLUE, capsize=2.5,
                    lw=1.0)
        for i, v in enumerate(variants):
            for r in grouped[v]:
                ax.plot(i, r["end_mid"], "o", color=NEUTRAL_MID, ms=2.5,
                        alpha=0.6, zorder=1)
                src.append({"base": mkt, "variant": v,
                            "end_mid": r["end_mid"]})
        ax.axhline(truth[mkt], ls="--", lw=0.8, color=RED, label=LEGEND_TRUTH)
        ax.set_xticks(xi)
        ax.set_xticklabels([PROFILE_VARIANT[v] for v in variants])
        ax.set_xlabel(XLABEL_PROFILE_MIX)
        ax.set_ylabel(YLABEL_END_MID)
        ax.set_ylim(-0.03, 1.03)
        ax.set_title(market_title(mkt), fontsize=7, color=NEUTRAL_DARK)
        ax.legend(loc="best", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_RQ4_PROFILE, source_data=pd.DataFrame(src))

    rows = []
    for mkt, grouped in by_mkt.items():
        for v in variants:
            em, es = _agg(grouped[v], "end_mid")
            vol, _ = _agg(grouped[v], "volatility")
            no, _ = _agg(grouped[v], "notional")
            f, _ = _agg(grouped[v], "n_fills")
            rows.append({"base": mkt, "variant": v,
                         "end_mid_mean": round(em, 3),
                         "end_mid_sd": round(es, 3),
                         "volatility": round(vol, 4),
                         "notional_mean": round(no, 0),
                         "fills_mean": round(f, 1)})
    pd.DataFrame(rows).to_csv(OUT_TBL / TBL_RQ4_PROFILE, index=False)


ACTION_ORDER = ["LIMIT", "MARKET", "CANCEL", "HOLD", "SPLIT",
                "MERGE", "UPDATE_BELIEF"]


def fig_rq4_thinking():
    by_mkt = {mkt: _grouped(f"c5_{mkt}", r"_(on|off)_")
              for mkt in ("robotaxi", "ethereum")}
    truth = {"robotaxi": truth_yes(metrics(runs_of("c1_robotaxi")[0])["slug"]),
             "ethereum": truth_yes(metrics(runs_of("c1_ethereum")[0])["slug"])}

    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=58))
    src = []
    for ax, (mkt, grouped) in zip(axes, by_mkt.items()):
        modes = ["on", "off"]
        width = 0.38
        xi = np.arange(len(ACTION_ORDER))
        for i, m in enumerate(modes):
            mix_avg = np.array([np.mean([r["action_mix"].get(a, 0.0)
                                          for r in grouped[m]])
                                for a in ACTION_ORDER])
            ax.bar(xi + (i - 0.5) * width, mix_avg, width,
                   color=(BLUE if m == "on" else NEUTRAL_DARK),
                   label=thinking_label(m))
            for a, v in zip(ACTION_ORDER, mix_avg):
                src.append({"base": mkt, "mode": m, "action": a,
                            "share_pct": float(v)})
        ax.set_xticks(xi)
        ax.set_xticklabels(ACTION_ORDER, rotation=45, ha="right", fontsize=6)
        ax.set_ylabel(XLABEL_ACTION_SHARE)
        ax.set_title(market_title(mkt), fontsize=7, color=NEUTRAL_DARK)
        ax.legend(loc="best", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_RQ4_THINKING, source_data=pd.DataFrame(src))

    rows = []
    for mkt, grouped in by_mkt.items():
        for m in ("on", "off"):
            em, es = _agg(grouped[m], "end_mid")
            vol, _ = _agg(grouped[m], "volatility")
            rows.append({"base": mkt, "mode": m,
                         "end_mid_mean": round(em, 3),
                         "end_mid_sd": round(es, 3),
                         "volatility": round(vol, 4)})
    pd.DataFrame(rows).to_csv(OUT_TBL / TBL_RQ4_THINKING, index=False)


# ──────────────────────────────────────────────────────────────────────
# RQ5 — open-market preview (rq5)
# ──────────────────────────────────────────────────────────────────────
def fig_rq5():
    rows_ = [metrics(r) for r in runs_of("rq5")]
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM + 20, 65))
    colors = {0: BLUE, 1: GREEN, 2: NEUTRAL_DARK}
    src = []
    for i, r in enumerate(rows_):
        m = r["mids"]
        ax.plot(m.index, m.to_numpy(), "-", color=colors[i], lw=1.0,
                label=seed_label(i))
        for t, v in m.items():
            src.append({"seed": i, "tick": int(t), "yes_mid": float(v)})
    start = np.mean([r["start_mid"] for r in rows_])
    ax.axhline(start, ls=":", lw=0.8, color=NEUTRAL_MID, label=LEGEND_MARKET_OPEN)
    ax.set_xlabel(XLABEL_DECISION_ROUND)
    ax.set_ylabel(XLABEL_YES_MID)
    ax.legend(loc="best", fontsize=6.5)
    finalize(fig, OUT_FIG / FIG_RQ5_OPEN, source_data=pd.DataFrame(src))

    out = []
    for i, r in enumerate(rows_):
        out.append({"seed": i,
                    "start_mid": round(r["start_mid"], 3),
                    "end_mid": round(r["end_mid"], 3),
                    "drift": round(r["end_mid"] - r["start_mid"], 3),
                    "volatility": round(r["volatility"], 4),
                    "n_fills": r["n_fills"]})
    pd.DataFrame(out).to_csv(OUT_TBL / TBL_RQ5_OPEN, index=False)


# ──────────────────────────────────────────────────────────────────────
def main():
    print("RQ1 panel …")
    fig_rq1()
    print("RQ2 scale …")
    fig_rq2()
    print("RQ3 tick …")
    fig_rq3()
    print("RQ4 profile-mix …")
    fig_rq4_profile()
    print("RQ4 thinking …")
    fig_rq4_thinking()
    print("RQ5 open preview …")
    fig_rq5()
    print(f"\nfigures → {OUT_FIG}")
    print(f"tables  → {OUT_TBL}")


if __name__ == "__main__":
    main()
