"""v14 extended analysis — additional figures with Chinese filenames.

Adds 17 figures and 1 table to docs/v14/, complementing the
per-RQ and decision-chain analyses already produced by
thesis_v14_analysis.py and thesis_v14_decision_chain.py.

Figure filenames and on-chart text use Chinese labels; action type codes
(LIMIT, MARKET, …) and parameter symbols such as n, t remain in English.

Run:  uv run python scripts/thesis_v14_extended.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _thesis_labels import (
    CB_DECISION_ROUND, CB_TRANSITION, LEGEND_MEAN_SEEDS, LEGEND_NO_MOVEMENT,
    LEGEND_OPEN_UNRESOLVED, LEGEND_START_PRICE, LEGEND_TRUTH_MARKER,
    LEGEND_TRUTH_NO, LEGEND_TRUTH_YES, XLABEL_ACTION_SHARE, XLABEL_AGENTS,
    XLABEL_BELIEF_DECLARED, XLABEL_BELIEF_MINUS_PRICE, XLABEL_BELIEF_UPDATES,
    XLABEL_CANCEL_SHARE, XLABEL_CONFIDENCE, XLABEL_DECISION_ROUND,
    XLABEL_END_YES, XLABEL_FILL_NOTIONAL, XLABEL_FILLS, XLABEL_FIRST_TRADE_TICK,
    XLABEL_HORIZON_FRAC, XLABEL_NEXT_ACTION, XLABEL_PREV_ACTION,
    XLABEL_START_YES, XLABEL_YES_MID, YLABEL_AGENT_PNL, YLABEL_BELIEF_STD,
    end_price_truth_no, end_price_truth_yes, first_belief_label, last_belief_label,
    market_title, mean_label, median_label, n_label, suite_title, t_label,
    XLABEL_YES_PROB,
)
from _thesis_style import (
    apply_style, finalize, fig_size, fig_size_vstack, panel_label,
    BLUE, BLUE_LIGHT, GREEN, GREEN_DEEP, RED, RED_LIGHT, TEAL, VIOLET, GOLD,
    NEUTRAL_LIGHT, NEUTRAL_MID, NEUTRAL_DARK, NEUTRAL_BLACK,
    COL_SINGLE_MM, COL_DOUBLE_MM,
)

apply_style()

ROOT = Path(__file__).resolve().parent.parent
OUT_FIG = ROOT / "docs" / "v14" / "figures"
OUT_TBL = ROOT / "docs" / "v14" / "tables"
OUT_FIG.mkdir(parents=True, exist_ok=True)
OUT_TBL.mkdir(parents=True, exist_ok=True)
V14 = ROOT / "output" / "v14"

FIG_ACTION_EVOLUTION = "决策链_动作组成随轮数演化"
FIG_BELIEF_DIST_START_END = "决策链_智能体信念分布始末对比"
FIG_PNL_BY_SCALE = "规模效应_不同智能体数量下个体盈亏分布"
FIG_PNL_BY_TICK = "时长效应_不同模拟轮数下个体盈亏分布"
FIG_PRICE_PATHS_C1 = "规模效应_不同智能体数量下价格路径全景"
FIG_PRICE_PATHS_C3 = "时长效应_不同模拟轮数下价格路径全景"
FIG_START_END_SCATTER = "行为可信性_全部仿真起点价与终点价关系"
FIG_CANCEL_OVER_TIME = "规模效应_不同智能体数量下撤单率随轮数变化"
FIG_BELIEF_PRICE_GAP = "决策链_群体信念与市场价格差异时间演化"
FIG_ACTION_TRANSITIONS = "决策链_相邻轮次动作转移矩阵"
FIG_BELIEF_UPDATE_HIST = "决策链_智能体信念更新次数分布"
FIG_BELIEF_STD = "决策链_群体信念离散度随轮数变化"
FIG_FIRST_TRADE_LATENCY = "决策链_智能体首次交易轮数分布"
FIG_FILL_SIZE_DIST = "规模效应_单笔成交名义额分布"
FIG_PNL_BY_CLUSTER = "模块消融_不同行为画像的个体盈亏分布"
FIG_BELIEF_CONFIDENCE = "决策链_声明信念与置信度关系"
FIG_PANEL_DIRECTION = "行为可信性_十市场起点终点漂移与真值标注"

TBL_ACTION_TRANSITIONS = "表_决策链_相邻轮次动作转移频次.csv"

ACTIONS = ["LIMIT", "MARKET", "CANCEL", "HOLD", "SPLIT", "MERGE",
           "UPDATE_BELIEF"]
ACTION_COLOR = {
    "LIMIT": BLUE, "MARKET": GREEN_DEEP, "CANCEL": RED,
    "HOLD": NEUTRAL_LIGHT, "SPLIT": TEAL, "MERGE": VIOLET,
    "UPDATE_BELIEF": GOLD,
}


def runs(suite):
    return sorted((V14 / suite).glob("2026*/"))


def config_name(run):
    return "-".join(run.name.split("-")[1:-2])


def load_actions(run):
    return pd.read_parquet(run / "raw" / "agent_actions.parquet")


def truth_yes(slug):
    p = ROOT / f"data/priors_{slug}.json"
    if not p.exists():
        return float("nan")
    d = json.loads(p.read_text())
    wi = d.get("winning_idx")
    if wi is None or wi < 0:
        return float("nan")
    return 1.0 if wi == 0 else 0.0


# ──────────────────────────────────────────────────────────────────────
# 决策链_动作组成随轮数演化.png
# ──────────────────────────────────────────────────────────────────────
def fig_action_evolution():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=58))
    for ax, suite in zip(axes, ("c5_robotaxi", "c5_ethereum")):
        # baseline run (thinking on, seed 0)
        run = next(r for r in runs(suite) if "_on_s0-" in r.name)
        a = load_actions(run)
        per = (a.groupby(["tick_idx", "action_type"]).size()
               .unstack(fill_value=0))
        per = per.reindex(columns=ACTIONS, fill_value=0)
        per_pct = per.div(per.sum(axis=1), axis=0) * 100
        cols = [c for c in ACTIONS if c in per_pct.columns]
        ax.stackplot(per_pct.index, *[per_pct[c] for c in cols],
                     colors=[ACTION_COLOR[c] for c in cols],
                     labels=cols, alpha=0.85)
        ax.set_xlabel(XLABEL_DECISION_ROUND)
        ax.set_ylabel(XLABEL_ACTION_SHARE if suite.endswith("robotaxi") else "")
        ax.set_title(suite_title(suite), fontsize=7, color=NEUTRAL_DARK)
        ax.set_ylim(0, 100)
        if suite.endswith("ethereum"):
            ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15),
                      ncol=4, fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_ACTION_EVOLUTION,
             source_data=None)


# ──────────────────────────────────────────────────────────────────────
# 决策链_智能体信念分布始末对比.png
# ──────────────────────────────────────────────────────────────────────
def fig_belief_dist_start_end():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=52))
    src = []
    for ax, suite in zip(axes, ("c5_robotaxi", "c5_ethereum")):
        starts, ends = [], []
        for run in runs(suite):
            if "_on_" not in run.name:
                continue
            a = load_actions(run)
            b = a[a.action_type == "UPDATE_BELIEF"]
            first = b.groupby("agent_id").first()["price"].tolist()
            last = b.groupby("agent_id").last()["price"].tolist()
            starts += first; ends += last
            for v in first:
                src.append({"suite": suite, "phase": "start", "yes_prob": v})
            for v in last:
                src.append({"suite": suite, "phase": "end", "yes_prob": v})
        bins = np.linspace(0, 1, 21)
        ax.hist(starts, bins=bins, color=NEUTRAL_MID, alpha=0.6,
                label=first_belief_label(len(starts)), edgecolor="white",
                linewidth=0.4)
        ax.hist(ends, bins=bins, color=BLUE, alpha=0.7,
                label=last_belief_label(len(ends)), edgecolor="white",
                linewidth=0.4)
        ax.axvline(np.mean(starts), ls=":", lw=0.7, color=NEUTRAL_DARK)
        ax.axvline(np.mean(ends), ls=":", lw=0.7, color=BLUE)
        ax.set_xlabel(XLABEL_BELIEF_DECLARED)
        ax.set_ylabel(XLABEL_AGENTS if suite.endswith("robotaxi") else "")
        ax.set_title(suite_title(suite), fontsize=7, color=NEUTRAL_DARK)
        ax.legend(loc="best", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_BELIEF_DIST_START_END,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 规模效应_不同智能体数量下个体盈亏分布.png
# ──────────────────────────────────────────────────────────────────────
def _agent_pnls(run):
    pos = pd.read_parquet(run / "raw" / "agent_positions.parquet")
    per = pd.read_parquet(run / "raw" / "agent_personas.parquet")
    last = pos.sort_values("tick_idx").groupby("agent_id").last().reset_index()
    m = last.merge(per[["agent_id", "capital_initial", "persona_type"]],
                   on="agent_id")
    m["pnl"] = m["cash"] + m["unrealized_pnl"] - m["capital_initial"]
    return m


def fig_pnl_by_scale():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=55))
    src = []
    for ax, mkt in zip(axes, ("robotaxi", "ethereum")):
        data, labels = [], []
        for n in (10, 20, 50, 100):
            pnls = []
            for r in runs(f"c1_{mkt}"):
                if f"_n{n}_" not in r.name:
                    continue
                m = _agent_pnls(r)
                pnls += m["pnl"].tolist()
                for p in m["pnl"]:
                    src.append({"market": mkt, "n_agents": n,
                                "pnl": float(p)})
            data.append(pnls); labels.append(f"n={n}")
        bp = ax.boxplot(data, labels=labels, widths=0.5,
                        showmeans=True, meanline=False,
                        patch_artist=True,
                        flierprops=dict(marker=".", markersize=1.5,
                                        markerfacecolor=NEUTRAL_MID,
                                        markeredgecolor="none", alpha=0.5))
        for patch in bp['boxes']:
            patch.set_facecolor(BLUE_LIGHT); patch.set_edgecolor(NEUTRAL_DARK)
            patch.set_linewidth(0.6)
        ax.axhline(0, ls=":", lw=0.6, color=NEUTRAL_DARK)
        ax.set_ylabel(YLABEL_AGENT_PNL if mkt == "robotaxi" else "")
        ax.set_title(market_title(mkt), fontsize=7, color=NEUTRAL_DARK)
    finalize(fig, OUT_FIG / FIG_PNL_BY_SCALE,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 时长效应_不同模拟轮数下个体盈亏分布.png
# ──────────────────────────────────────────────────────────────────────
def fig_pnl_by_tick():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=55))
    src = []
    for ax, mkt in zip(axes, ("robotaxi", "ethereum")):
        data, labels = [], []
        for t in (10, 20, 50, 100):
            pnls = []
            for r in runs(f"c3_{mkt}"):
                if f"_t{t}_" not in r.name:
                    continue
                m = _agent_pnls(r)
                pnls += m["pnl"].tolist()
                for p in m["pnl"]:
                    src.append({"market": mkt, "n_ticks": t,
                                "pnl": float(p)})
            data.append(pnls); labels.append(f"t={t}")
        bp = ax.boxplot(data, labels=labels, widths=0.5,
                        patch_artist=True,
                        flierprops=dict(marker=".", markersize=1.5,
                                        markerfacecolor=NEUTRAL_MID,
                                        markeredgecolor="none", alpha=0.5))
        for patch in bp['boxes']:
            patch.set_facecolor(GREEN); patch.set_edgecolor(NEUTRAL_DARK)
            patch.set_linewidth(0.6)
        ax.axhline(0, ls=":", lw=0.6, color=NEUTRAL_DARK)
        ax.set_ylabel(YLABEL_AGENT_PNL if mkt == "robotaxi" else "")
        ax.set_title(market_title(mkt), fontsize=7, color=NEUTRAL_DARK)
    finalize(fig, OUT_FIG / FIG_PNL_BY_TICK,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 规模效应_不同智能体数量下价格路径全景.png
# ──────────────────────────────────────────────────────────────────────
def _yes_mid(run):
    a = load_actions(run)
    return (a.dropna(subset=["yes_mid_after"])
            .groupby("tick_idx").yes_mid_after.last())


def fig_price_paths_c1():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=55))
    colors = {10: BLUE, 20: GREEN, 50: NEUTRAL_DARK, 100: RED}
    src = []
    for ax, mkt in zip(axes, ("robotaxi", "ethereum")):
        truth = truth_yes(json.loads(
            (runs(f"c1_{mkt}")[0] / "meta.json").read_text()
        )["config"]["market"]["slug"])
        for r in runs(f"c1_{mkt}"):
            mo = re.search(r"_n(\d+)_", config_name(r))
            n = int(mo.group(1))
            mids = _yes_mid(r)
            ax.plot(mids.index, mids.to_numpy(), "-", color=colors[n],
                    lw=0.7, alpha=0.55)
            for ti, v in mids.items():
                src.append({"market": mkt, "n": n, "tick": int(ti),
                            "yes_mid": float(v)})
        ax.axhline(truth, ls="--", lw=0.8, color=RED)
        for n, c in colors.items():
            ax.plot([], [], "-", color=c, label=n_label(n))
        ax.set_xlabel(XLABEL_DECISION_ROUND)
        ax.set_ylabel(XLABEL_YES_MID if mkt == "robotaxi" else "")
        ax.set_title(market_title(mkt), fontsize=7, color=NEUTRAL_DARK)
        ax.set_ylim(-0.03, 1.03)
        ax.legend(loc="best", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_PRICE_PATHS_C1,
             source_data=pd.DataFrame(src))


def fig_price_paths_c3():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=55))
    colors = {10: BLUE, 20: GREEN, 50: NEUTRAL_DARK, 100: RED}
    src = []
    for ax, mkt in zip(axes, ("robotaxi", "ethereum")):
        truth = truth_yes(json.loads(
            (runs(f"c3_{mkt}")[0] / "meta.json").read_text()
        )["config"]["market"]["slug"])
        for r in runs(f"c3_{mkt}"):
            mo = re.search(r"_t(\d+)_", config_name(r))
            t = int(mo.group(1))
            mids = _yes_mid(r)
            # normalize by horizon length
            frac = np.linspace(0, 1, len(mids))
            ax.plot(frac, mids.to_numpy(), "-", color=colors[t],
                    lw=0.7, alpha=0.55)
            for fr, v in zip(frac, mids.to_numpy()):
                src.append({"market": mkt, "n_ticks": t,
                            "frac": float(fr), "yes_mid": float(v)})
        ax.axhline(truth, ls="--", lw=0.8, color=RED)
        for t, c in colors.items():
            ax.plot([], [], "-", color=c, label=t_label(t))
        ax.set_xlabel(XLABEL_HORIZON_FRAC)
        ax.set_ylabel(XLABEL_YES_MID if mkt == "robotaxi" else "")
        ax.set_title(market_title(mkt), fontsize=7, color=NEUTRAL_DARK)
        ax.set_ylim(-0.03, 1.03)
        ax.legend(loc="best", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_PRICE_PATHS_C3,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 行为可信性_全部仿真起点价与终点价关系.png
# ──────────────────────────────────────────────────────────────────────
def fig_start_end_scatter():
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM + 25, 75))
    src = []
    for suite_dir in sorted(V14.glob("*/")):
        if not suite_dir.is_dir():
            continue
        for run in suite_dir.glob("2026*/"):
            if not (run / "analysis" / "summary.json").exists():
                continue
            slug = json.loads((run / "meta.json").read_text())["config"]["market"]["slug"]
            t = truth_yes(slug)
            mids = _yes_mid(run)
            sm, em = float(mids.iloc[0]), float(mids.iloc[-1])
            color = GREEN if t == 1.0 else (RED if t == 0.0 else NEUTRAL_MID)
            ax.plot(sm, em, "o", color=color, ms=3, alpha=0.6,
                    markeredgecolor="none")
            src.append({"suite": suite_dir.name,
                        "start_mid": sm, "end_mid": em,
                        "truth": t, "slug": slug})
    # 45° line (no price discovery → end = start)
    ax.plot([0, 1], [0, 1], ls="--", lw=0.7, color=NEUTRAL_DARK,
            label=LEGEND_NO_MOVEMENT)
    ax.plot([], [], "o", color=GREEN, label=LEGEND_TRUTH_YES)
    ax.plot([], [], "o", color=RED, label=LEGEND_TRUTH_NO)
    ax.plot([], [], "o", color=NEUTRAL_MID, label=LEGEND_OPEN_UNRESOLVED)
    ax.set_xlabel(XLABEL_START_YES)
    ax.set_ylabel(XLABEL_END_YES)
    ax.set_xlim(-0.03, 1.03); ax.set_ylim(-0.03, 1.03)
    ax.legend(loc="best", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_START_END_SCATTER,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 规模效应_不同智能体数量下撤单率随轮数变化.png
# ──────────────────────────────────────────────────────────────────────
def fig_cancel_over_time():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=55))
    colors = {10: BLUE, 20: GREEN, 50: NEUTRAL_DARK, 100: RED}
    src = []
    for ax, mkt in zip(axes, ("robotaxi", "ethereum")):
        for n in (10, 20, 50, 100):
            per_tick = []
            for r in runs(f"c1_{mkt}"):
                if f"_n{n}_" not in r.name:
                    continue
                a = load_actions(r)
                rate = (a.groupby("tick_idx")
                          .apply(lambda x: (x.action_type == "CANCEL").mean() * 100))
                per_tick.append(rate)
            if not per_tick:
                continue
            # align lengths
            L = min(len(s) for s in per_tick)
            arr = np.array([s.to_numpy()[:L] for s in per_tick])
            mean = arr.mean(axis=0)
            ax.plot(range(L), mean, "-", color=colors[n], lw=1.0,
                    label=n_label(n))
            for ti, v in enumerate(mean):
                src.append({"market": mkt, "n": n, "tick": ti,
                            "cancel_pct": float(v)})
        ax.set_xlabel(XLABEL_DECISION_ROUND)
        ax.set_ylabel(XLABEL_CANCEL_SHARE if mkt == "robotaxi" else "")
        ax.set_title(market_title(mkt), fontsize=7, color=NEUTRAL_DARK)
        ax.legend(loc="best", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_CANCEL_OVER_TIME,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 决策链_群体信念与市场价格差异时间演化.png
# ──────────────────────────────────────────────────────────────────────
def fig_belief_price_gap_evo():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=55))
    src = []
    for ax, suite in zip(axes, ("c5_robotaxi", "c5_ethereum")):
        per_tick_gap = []
        for run in runs(suite):
            if "_on_" not in run.name:
                continue
            a = load_actions(run)
            mids = (a.dropna(subset=["yes_mid_after"])
                    .groupby("tick_idx").yes_mid_after.last())
            b = a[a.action_type == "UPDATE_BELIEF"]
            # for each tick: mean belief across agents who updated by that tick
            mean_belief = b.groupby("tick_idx")["price"].mean()
            gap = mean_belief.reindex(mids.index).ffill() - mids
            per_tick_gap.append(gap)
        if not per_tick_gap:
            continue
        L = min(len(s) for s in per_tick_gap)
        arr = np.array([s.to_numpy()[:L] for s in per_tick_gap])
        mean = arr.mean(axis=0); sd = arr.std(axis=0)
        ax.fill_between(range(L), mean - sd, mean + sd, color=BLUE_LIGHT,
                        alpha=0.3)
        ax.plot(range(L), mean, "-", color=BLUE, lw=1.2,
                label=LEGEND_MEAN_SEEDS)
        ax.axhline(0, ls=":", lw=0.6, color=NEUTRAL_DARK)
        ax.set_xlabel(XLABEL_DECISION_ROUND)
        ax.set_ylabel(XLABEL_BELIEF_MINUS_PRICE
                      if suite.endswith("robotaxi") else "")
        ax.set_title(suite_title(suite), fontsize=7, color=NEUTRAL_DARK)
        ax.legend(loc="best", fontsize=6.0)
        for ti, v in enumerate(mean):
            src.append({"suite": suite, "tick": ti, "mean_gap": float(v)})
    finalize(fig, OUT_FIG / FIG_BELIEF_PRICE_GAP,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 决策链_相邻轮次动作转移矩阵.png
# ──────────────────────────────────────────────────────────────────────
def fig_action_transitions():
    suite = "c5_robotaxi"
    counts = np.zeros((len(ACTIONS), len(ACTIONS)), dtype=int)
    idx = {a: i for i, a in enumerate(ACTIONS)}
    for run in runs(suite):
        if "_on_s0-" not in run.name:
            continue
        a = load_actions(run)
        for aid, sub in a.groupby("agent_id"):
            seq = sub.sort_values("tick_idx")["action_type"].tolist()
            for prev, nxt in zip(seq, seq[1:]):
                if prev in idx and nxt in idx:
                    counts[idx[prev], idx[nxt]] += 1
    # row-normalize
    norm = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1) * 100
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM + 25, 70))
    im = ax.imshow(norm, cmap="Blues", vmin=0, vmax=60)
    ax.set_xticks(range(len(ACTIONS)))
    ax.set_xticklabels(ACTIONS, rotation=45, ha="right", fontsize=6.0)
    ax.set_yticks(range(len(ACTIONS)))
    ax.set_yticklabels(ACTIONS, fontsize=6.0)
    ax.set_xlabel(XLABEL_NEXT_ACTION)
    ax.set_ylabel(XLABEL_PREV_ACTION)
    cb = plt.colorbar(im, ax=ax, shrink=0.7, pad=0.02)
    cb.set_label(CB_TRANSITION, fontsize=6.0)
    for i in range(len(ACTIONS)):
        for j in range(len(ACTIONS)):
            if norm[i, j] > 30:
                ax.text(j, i, f"{norm[i, j]:.0f}", ha="center", va="center",
                        fontsize=5.5, color="white")
    finalize(fig, OUT_FIG / FIG_ACTION_TRANSITIONS, source_data=None)
    pd.DataFrame(norm.round(1),
                 index=ACTIONS, columns=ACTIONS).to_csv(
        OUT_TBL / TBL_ACTION_TRANSITIONS)


# ──────────────────────────────────────────────────────────────────────
# 决策链_智能体信念更新次数分布.png
# ──────────────────────────────────────────────────────────────────────
def fig_belief_update_hist():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=52))
    src = []
    for ax, suite in zip(axes, ("c5_robotaxi", "c5_ethereum")):
        counts = []
        for run in runs(suite):
            a = load_actions(run)
            per = (a[a.action_type == "UPDATE_BELIEF"]
                   .groupby("agent_id").size())
            counts += per.tolist()
            for v in per:
                src.append({"suite": suite, "n_updates": int(v)})
        ax.hist(counts, bins=range(0, 22), color=BLUE, edgecolor=NEUTRAL_DARK,
                linewidth=0.5)
        ax.axvline(np.mean(counts), ls="--", lw=0.8, color=RED,
                   label=mean_label(np.mean(counts), digits=1))
        ax.set_xlabel(XLABEL_BELIEF_UPDATES)
        ax.set_ylabel(XLABEL_AGENTS if suite.endswith("robotaxi") else "")
        ax.set_title(suite_title(suite), fontsize=7, color=NEUTRAL_DARK)
        ax.legend(loc="best", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_BELIEF_UPDATE_HIST,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 决策链_群体信念离散度随轮数变化.png
# ──────────────────────────────────────────────────────────────────────
def fig_belief_std_evo():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=52))
    src = []
    for ax, suite in zip(axes, ("c5_robotaxi", "c5_ethereum")):
        per_tick = []
        for run in runs(suite):
            if "_on_" not in run.name:
                continue
            a = load_actions(run)
            b = a[a.action_type == "UPDATE_BELIEF"]
            # for each tick, std across the latest declared belief of every agent
            seen: dict = {}
            stds = []
            for ti, sub in b.groupby("tick_idx"):
                for _, row in sub.iterrows():
                    seen[int(row["agent_id"])] = float(row["price"])
                if len(seen) >= 3:
                    stds.append((ti, np.std(list(seen.values()), ddof=1)))
            if stds:
                per_tick.append(pd.Series([s for _, s in stds],
                                          index=[t for t, _ in stds]))
        if not per_tick:
            continue
        L = min(len(s) for s in per_tick)
        arr = np.array([s.to_numpy()[:L] for s in per_tick])
        mean = arr.mean(axis=0); sd = arr.std(axis=0)
        x = list(per_tick[0].index[:L])
        ax.fill_between(x, mean - sd, mean + sd, color=BLUE_LIGHT, alpha=0.3)
        ax.plot(x, mean, "-", color=BLUE, lw=1.2)
        ax.set_xlabel(XLABEL_DECISION_ROUND)
        ax.set_ylabel(YLABEL_BELIEF_STD if suite.endswith("robotaxi") else "")
        ax.set_title(suite_title(suite), fontsize=7, color=NEUTRAL_DARK)
        for ti, v in zip(x, mean):
            src.append({"suite": suite, "tick": int(ti),
                        "belief_std": float(v)})
    finalize(fig, OUT_FIG / FIG_BELIEF_STD,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 决策链_智能体首次交易轮数分布.png
# ──────────────────────────────────────────────────────────────────────
def fig_first_trade_latency():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=52))
    src = []
    for ax, mkt in zip(axes, ("robotaxi", "ethereum")):
        data = []
        for r in runs(f"c5_{mkt}"):
            if "_on_" not in r.name:
                continue
            a = load_actions(r)
            trades = a[a.action_type.isin(("LIMIT", "MARKET"))]
            first = (trades.groupby("agent_id")["tick_idx"].min())
            data += first.tolist()
            for v in first:
                src.append({"market": mkt, "first_trade_tick": int(v)})
        ax.hist(data, bins=range(0, 21), color=GREEN, edgecolor=NEUTRAL_DARK,
                linewidth=0.5)
        ax.axvline(np.mean(data), ls="--", lw=0.8, color=RED,
                   label=mean_label(np.mean(data), digits=1))
        ax.set_xlabel(XLABEL_FIRST_TRADE_TICK)
        ax.set_ylabel(XLABEL_AGENTS if mkt == "robotaxi" else "")
        ax.set_title(market_title(mkt), fontsize=7, color=NEUTRAL_DARK)
        ax.legend(loc="best", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_FIRST_TRADE_LATENCY,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 规模效应_单笔成交名义额分布.png
# ──────────────────────────────────────────────────────────────────────
def fig_fill_size_dist():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=52))
    src = []
    for ax, mkt in zip(axes, ("robotaxi", "ethereum")):
        sizes = []
        # combine all c1 runs at n=50 for a rich sample
        for r in runs(f"c1_{mkt}"):
            if "_n50_" not in r.name:
                continue
            f = pd.read_parquet(r / "raw" / "agent_fills.parquet")
            sizes += f["notional"].tolist()
            for v in f["notional"]:
                src.append({"market": mkt, "notional": float(v)})
        if not sizes:
            continue
        ax.hist(sizes, bins=np.logspace(0, 4, 40), color=BLUE,
                edgecolor=NEUTRAL_DARK, linewidth=0.4)
        ax.set_xscale("log")
        ax.axvline(np.median(sizes), ls="--", lw=0.8, color=RED,
                   label=median_label(np.median(sizes)))
        ax.set_xlabel(XLABEL_FILL_NOTIONAL)
        ax.set_ylabel(XLABEL_FILLS if mkt == "robotaxi" else "")
        ax.set_title(f"{market_title(mkt)}（n=50 仿真）", fontsize=7,
                     color=NEUTRAL_DARK)
        ax.legend(loc="best", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_FILL_SIZE_DIST,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 模块消融_不同行为画像的个体盈亏分布.png
# ──────────────────────────────────────────────────────────────────────
def fig_pnl_by_cluster():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=55))
    src = []
    for ax, mkt in zip(axes, ("robotaxi", "ethereum")):
        all_pnls = {}  # cluster_label -> pnl list
        for r in runs(f"c1_{mkt}"):
            try:
                m = _agent_pnls(r)
            except Exception:
                continue
            for cl, p in zip(m["persona_type"], m["pnl"]):
                all_pnls.setdefault(cl, []).append(p)
                src.append({"market": mkt, "cluster": cl, "pnl": float(p)})
        clusters = sorted(all_pnls.keys())
        data = [all_pnls[c] for c in clusters]
        bp = ax.boxplot(data, labels=clusters, widths=0.6, showmeans=True,
                        patch_artist=True,
                        flierprops=dict(marker=".", markersize=1.2,
                                        markerfacecolor=NEUTRAL_MID,
                                        markeredgecolor="none", alpha=0.4))
        for patch in bp['boxes']:
            patch.set_facecolor(TEAL); patch.set_edgecolor(NEUTRAL_DARK)
            patch.set_linewidth(0.5); patch.set_alpha(0.7)
        ax.axhline(0, ls=":", lw=0.6, color=NEUTRAL_DARK)
        ax.set_ylabel(YLABEL_AGENT_PNL if mkt == "robotaxi" else "")
        ax.set_title(f"{market_title(mkt)}（全部 c1 仿真）", fontsize=7,
                     color=NEUTRAL_DARK)
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=5.5)
    finalize(fig, OUT_FIG / FIG_PNL_BY_CLUSTER,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# 决策链_声明信念与置信度关系.png
# ──────────────────────────────────────────────────────────────────────
def fig_belief_confidence():
    suite = "c5_robotaxi"
    rows = []
    for run in runs(suite):
        if "_on_" not in run.name:
            continue
        a = load_actions(run)
        b = a[a.action_type == "UPDATE_BELIEF"]
        for _, r in b.iterrows():
            try:
                raw = json.loads(r["raw_response"])
                if "belief_update" in raw:
                    args = raw["belief_update"]
                else:
                    tc = raw["choices"][0]["message"].get("tool_calls") or []
                    if not tc:
                        continue
                    args = json.loads(tc[0]["function"]["arguments"])
                rows.append({"yes_prob": float(args.get("yes_prob", 0.5)),
                             "confidence": float(args.get("confidence", 0.5)),
                             "tick": int(r["tick_idx"])})
            except Exception:
                continue
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM + 25, 75))
    sc = ax.scatter(df["yes_prob"], df["confidence"], c=df["tick"],
                    cmap="viridis", s=8, alpha=0.5, edgecolors="none")
    ax.set_xlim(-0.03, 1.03); ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel(XLABEL_BELIEF_DECLARED)
    ax.set_ylabel(XLABEL_CONFIDENCE)
    cb = plt.colorbar(sc, ax=ax, shrink=0.7, pad=0.02)
    cb.set_label(CB_DECISION_ROUND, fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_BELIEF_CONFIDENCE, source_data=df)


# ──────────────────────────────────────────────────────────────────────
# 行为可信性_十市场起点终点漂移与真值标注.png
# ──────────────────────────────────────────────────────────────────────
def fig_panel_direction():
    """rq1 panel: show start/end with arrow toward/away from truth, one row per market."""
    rows = []
    for run in runs("rq1"):
        if not (run / "analysis" / "summary.json").exists():
            continue
        slug = json.loads((run / "meta.json").read_text())["config"]["market"]["slug"]
        mids = _yes_mid(run)
        rows.append({"slug": slug, "truth": truth_yes(slug),
                     "start": float(mids.iloc[0]),
                     "end": float(mids.iloc[-1])})
    df = pd.DataFrame(rows)
    # short labels
    short = {}
    for s in df.slug.unique():
        short[s] = s[:34] + "…" if len(s) > 34 else s
    grouped = df.groupby("slug").agg(start=("start", "mean"),
                                     end=("end", "mean"),
                                     truth=("truth", "first")).reset_index()
    grouped = grouped.sort_values(["truth", "start"])
    fig, ax = plt.subplots(figsize=fig_size(COL_DOUBLE_MM, 95))
    y = np.arange(len(grouped))
    for i, row in enumerate(grouped.itertuples(index=False)):
        sm, em = row.start, row.end
        col = GREEN if row.truth == 1.0 else RED
        ax.plot([sm, em], [i, i], "-", color=col, lw=1.0, alpha=0.5)
        ax.plot(sm, i, "o", color=NEUTRAL_DARK, ms=3,
                markeredgecolor="white")
        ax.plot(em, i, ">" if em > sm else "<", color=col, ms=5,
                markeredgecolor="white")
        ax.plot(row.truth, i, "*", color=col, ms=8, markeredgecolor="white")
    ax.set_yticks(y)
    ax.set_yticklabels([short[s] for s in grouped.slug], fontsize=6.0)
    ax.set_xlim(-0.05, 1.05)
    ax.set_xlabel(XLABEL_YES_PROB)
    ax.plot([], [], "o", color=NEUTRAL_DARK, label=LEGEND_START_PRICE)
    ax.plot([], [], ">", color=GREEN, label=end_price_truth_yes())
    ax.plot([], [], "<", color=RED, label=end_price_truth_no())
    ax.plot([], [], "*", color=NEUTRAL_DARK, label=LEGEND_TRUTH_MARKER)
    ax.legend(loc="lower right", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_PANEL_DIRECTION, source_data=grouped)


# ──────────────────────────────────────────────────────────────────────
def main():
    print(FIG_ACTION_EVOLUTION)
    fig_action_evolution()
    print(FIG_BELIEF_DIST_START_END)
    fig_belief_dist_start_end()
    print(FIG_PNL_BY_SCALE)
    fig_pnl_by_scale()
    print(FIG_PNL_BY_TICK)
    fig_pnl_by_tick()
    print(FIG_PRICE_PATHS_C1)
    fig_price_paths_c1()
    print(FIG_PRICE_PATHS_C3)
    fig_price_paths_c3()
    print(FIG_START_END_SCATTER)
    fig_start_end_scatter()
    print(FIG_CANCEL_OVER_TIME)
    fig_cancel_over_time()
    print(FIG_BELIEF_PRICE_GAP)
    fig_belief_price_gap_evo()
    print(FIG_ACTION_TRANSITIONS)
    fig_action_transitions()
    print(FIG_BELIEF_UPDATE_HIST)
    fig_belief_update_hist()
    print(FIG_BELIEF_STD)
    fig_belief_std_evo()
    print(FIG_FIRST_TRADE_LATENCY)
    fig_first_trade_latency()
    print(FIG_FILL_SIZE_DIST)
    fig_fill_size_dist()
    print(FIG_PNL_BY_CLUSTER)
    fig_pnl_by_cluster()
    print(FIG_BELIEF_CONFIDENCE)
    fig_belief_confidence()
    print(FIG_PANEL_DIRECTION)
    fig_panel_direction()
    print(f"\n→ figures: {OUT_FIG}")


if __name__ == "__main__":
    main()
