"""v14 agent decision-chain analysis.

Looks INSIDE the simulation: how each agent updates its declared belief
over time, whether its trades line up with that belief, and how it uses
the available action repertoire.

Outputs (under docs/v14/figures and docs/v14/tables):
  决策链_智能体信念轨迹与市场价格
  决策链_信念与交易方向一致性
  决策链_智能体动作偏好热图
  表_决策链_信念行为一致性汇总.csv

The belief panel uses one representative run per base market (thinking
on, seed 0). The consistency and specialisation panels aggregate across
the c5 thinking-on suite of both base markets.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _thesis_labels import (
    CB_ACTION_SHARE, CB_DECISION_ROUND, CB_TRANSITION,
    LEGEND_CHANCE, LEGEND_FINAL_PRICE, LEGEND_MARKET_OPEN, LEGEND_MARKET_YES_MID,
    LEGEND_MEAN_BELIEF, LEGEND_MEAN_SEEDS, LEGEND_NO_MOVEMENT, LEGEND_OPEN_UNRESOLVED,
    LEGEND_START_PRICE, LEGEND_TRUTH_MARKER, LEGEND_TRUTH_NO, LEGEND_TRUTH_YES,
    XLABEL_ACTION_SHARE, XLABEL_AGENTS, XLABEL_BELIEF_DECLARED, XLABEL_BELIEF_MINUS_PRICE,
    XLABEL_BELIEF_UPDATES, XLABEL_CANCEL_SHARE, XLABEL_CONFIDENCE,
    XLABEL_DECISION_ROUND, XLABEL_END_YES, XLABEL_FILL_NOTIONAL, XLABEL_FILLS,
    XLABEL_FIRST_TRADE_TICK, XLABEL_HORIZON_FRAC, XLABEL_N_SIMULATIONS,
    XLABEL_NEXT_ACTION, XLABEL_PREV_ACTION, XLABEL_START_YES, XLABEL_TRADE_CONSISTENCY,
    XLABEL_TRADE_COUNT, XLABEL_YES_MID, XLABEL_YES_PROB,
    YLABEL_AGENT_PNL, YLABEL_AGENTS_SORTED, YLABEL_BELIEF_STD,
    consistent_label, end_price_truth_no, end_price_truth_yes, first_belief_label,
    inconsistent_label, last_belief_label, market_title, mean_label, median_label,
    n_label, seed_label, suite_title, t_label,
)
from _thesis_style import (
    apply_style, finalize, fig_size, fig_size_vstack, panel_label,
    BLUE, GREEN, RED, NEUTRAL_LIGHT, NEUTRAL_MID, NEUTRAL_DARK,
    COL_SINGLE_MM, COL_DOUBLE_MM,
)

apply_style()

ROOT = Path(__file__).resolve().parent.parent
OUT_FIG = ROOT / "docs" / "v14" / "figures"
OUT_TBL = ROOT / "docs" / "v14" / "tables"
OUT_FIG.mkdir(parents=True, exist_ok=True)
OUT_TBL.mkdir(parents=True, exist_ok=True)
V14 = ROOT / "output" / "v14"

FIG_DECISION_BELIEF = "决策链_智能体信念轨迹与市场价格"
FIG_DECISION_CONSISTENCY = "决策链_信念与交易方向一致性"
FIG_DECISION_ACTIONS = "决策链_智能体动作偏好热图"
TBL_DECISION_SUMMARY = "表_决策链_信念行为一致性汇总.csv"

ACTION_ORDER = ["LIMIT", "MARKET", "CANCEL", "HOLD", "SPLIT",
                "MERGE", "UPDATE_BELIEF"]


# ──────────────────────────────────────────────────────────────────────
def find_run(suite: str, config_substr: str) -> Path:
    for r in (V14 / suite).glob("2026*/"):
        if config_substr in r.name:
            return r
    raise FileNotFoundError(f"no run for {suite}/{config_substr}")


def load_actions(run: Path) -> pd.DataFrame:
    return pd.read_parquet(run / "raw" / "agent_actions.parquet")


# ──────────────────────────────────────────────────────────────────────
# Fig 1 — per-agent belief trajectories vs market price (2 base markets)
# ──────────────────────────────────────────────────────────────────────
def fig_belief():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=58))
    src = []
    for ax, (mkt, suite) in zip(axes, [
        ("Tesla Robotaxi", "c5_robotaxi"),
        ("Ethereum $5K",   "c5_ethereum"),
    ]):
        run = find_run(suite, "_on_s0-")
        a = load_actions(run)
        # belief updates only
        b = a[a.action_type == "UPDATE_BELIEF"].copy()
        # market price per tick (last yes_mid_after)
        mids = (a.dropna(subset=["yes_mid_after"])
                .groupby("tick_idx").yes_mid_after.last())
        # trajectories: each agent's declared yes_prob ordered by tick
        agents = sorted(b["agent_id"].unique())
        for aid in agents:
            sub = b[b["agent_id"] == aid].sort_values("tick_idx")
            ax.plot(sub["tick_idx"], sub["price"], "-",
                    color=NEUTRAL_LIGHT, lw=0.5, alpha=0.7)
            for _, row in sub.iterrows():
                src.append({"market": mkt, "agent_id": int(aid),
                            "tick": int(row["tick_idx"]),
                            "yes_prob": float(row["price"])})
        # market price overlay
        ax.plot(mids.index, mids.to_numpy(), "-", color=BLUE, lw=1.4,
                label=LEGEND_MARKET_YES_MID)
        # mean belief at each tick
        mean_b = b.groupby("tick_idx")["price"].mean()
        ax.plot(mean_b.index, mean_b.to_numpy(), "--", color=RED, lw=1.2,
                label=LEGEND_MEAN_BELIEF)
        ax.set_xlabel(XLABEL_DECISION_ROUND)
        ax.set_ylabel(XLABEL_YES_PROB if mkt.startswith("Tesla") else "")
        ax.set_title(mkt, fontsize=7, color=NEUTRAL_DARK)
        ax.set_ylim(-0.03, 1.03)
        ax.legend(loc="best", fontsize=6.0)
    finalize(fig, OUT_FIG / FIG_DECISION_BELIEF,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# Fig 2 — belief→trade consistency, aggregated across c5 thinking-on
# ──────────────────────────────────────────────────────────────────────
def _per_agent_last_belief(actions: pd.DataFrame) -> dict:
    """Track each agent's most-recent declared yes_prob as ticks advance.
    Returns {(agent_id, tick_idx): last_yes_prob}."""
    b = actions[actions.action_type == "UPDATE_BELIEF"].sort_values(
        ["agent_id", "tick_idx"])
    out: dict = {}
    for _, row in b.iterrows():
        out[(int(row["agent_id"]), int(row["tick_idx"]))] = float(row["price"])
    return out


def classify_trade(side: str, outcome: str) -> str:
    """Reduce to BUY_YES / SELL_YES (treat NO side as flipped YES)."""
    s = str(side).upper(); o = str(outcome).upper()
    if s == "BUY" and o == "YES": return "BUY_YES"
    if s == "SELL" and o == "YES": return "SELL_YES"
    if s == "BUY" and o == "NO": return "SELL_YES"
    if s == "SELL" and o == "NO": return "BUY_YES"
    return "OTHER"


def belief_consistency_for(run: Path) -> dict:
    a = load_actions(run)
    belief_at = {}
    # play forward: keep last declared belief per agent
    rows_consistent = 0; rows_total = 0
    diffs_consistent = []; diffs_inconsistent = []
    for _, row in a.sort_values(["tick_idx", "agent_id"]).iterrows():
        aid = int(row["agent_id"]); tick = int(row["tick_idx"])
        if row["action_type"] == "UPDATE_BELIEF":
            belief_at[aid] = float(row["price"])
            continue
        if row["action_type"] not in ("LIMIT", "MARKET"):
            continue
        b = belief_at.get(aid)
        if b is None: continue
        mid = row["yes_mid_before"]
        if mid is None or np.isnan(mid): continue
        trade_dir = classify_trade(row["side"], row["outcome"])
        if trade_dir == "OTHER": continue
        rows_total += 1
        # "consistent": BUY_YES when belief > market; SELL_YES when belief < market
        diff = b - mid
        ok = (trade_dir == "BUY_YES" and diff > 0) or \
             (trade_dir == "SELL_YES" and diff < 0)
        if ok:
            rows_consistent += 1
            diffs_consistent.append(diff)
        else:
            diffs_inconsistent.append(diff)
    return {
        "n_trades": rows_total,
        "n_consistent": rows_consistent,
        "frac_consistent": rows_consistent / rows_total if rows_total else 0.0,
        "diff_consistent": diffs_consistent,
        "diff_inconsistent": diffs_inconsistent,
    }


def fig_consistency():
    suites = ("c5_robotaxi", "c5_ethereum")
    all_diffs_c, all_diffs_i = [], []
    summary = []
    for suite in suites:
        for run in (V14 / suite).glob("2026*/"):
            if "_on_" not in run.name: continue
            r = belief_consistency_for(run)
            all_diffs_c += r["diff_consistent"]
            all_diffs_i += r["diff_inconsistent"]
            summary.append({"suite": suite, "run": run.name[:30],
                            "n_trades": r["n_trades"],
                            "frac_consistent": round(r["frac_consistent"], 3)})

    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=52))

    # panel a — bar: fraction of trades consistent with belief
    ax = axes[0]
    fracs = [s["frac_consistent"] for s in summary]
    ax.hist(fracs, bins=np.linspace(0.4, 1.0, 13),
            color=BLUE, edgecolor=NEUTRAL_DARK, linewidth=0.6)
    ax.axvline(np.mean(fracs), ls="--", lw=1.0, color=RED,
               label=mean_label(np.mean(fracs)))
    ax.axvline(0.5, ls=":", lw=0.7, color=NEUTRAL_MID, label=LEGEND_CHANCE)
    ax.set_xlabel(XLABEL_TRADE_CONSISTENCY)
    ax.set_ylabel(XLABEL_N_SIMULATIONS)
    ax.legend(loc="best", fontsize=6.0)
    panel_label(ax, "a")

    # panel b — distribution of belief−price gap, consistent vs inconsistent
    ax = axes[1]
    if all_diffs_c and all_diffs_i:
        bins = np.linspace(-1, 1, 40)
        ax.hist(all_diffs_c, bins=bins, color=GREEN, alpha=0.6,
                label=consistent_label(len(all_diffs_c)))
        ax.hist(all_diffs_i, bins=bins, color=RED, alpha=0.6,
                label=inconsistent_label(len(all_diffs_i)))
    ax.axvline(0, ls=":", lw=0.7, color=NEUTRAL_DARK)
    ax.set_xlabel(XLABEL_BELIEF_MINUS_PRICE)
    ax.set_ylabel(XLABEL_TRADE_COUNT)
    ax.legend(loc="best", fontsize=6.0)
    panel_label(ax, "b")

    finalize(fig, OUT_FIG / FIG_DECISION_CONSISTENCY,
             source_data=pd.DataFrame(summary))


# ──────────────────────────────────────────────────────────────────────
# Fig 3 — action specialisation per agent
# ──────────────────────────────────────────────────────────────────────
def fig_actions():
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=58))
    src = []
    for ax, (mkt, suite) in zip(axes, [
        ("Tesla Robotaxi", "c5_robotaxi"),
        ("Ethereum $5K",   "c5_ethereum"),
    ]):
        run = find_run(suite, "_on_s0-")
        a = load_actions(run)
        # per-agent action mix
        per = (a.groupby(["agent_id", "action_type"]).size()
               .unstack(fill_value=0))
        per = per.reindex(columns=ACTION_ORDER, fill_value=0)
        per_pct = per.div(per.sum(axis=1), axis=0) * 100
        # for each agent, what fraction is the dominant action
        dom_pct = per_pct.max(axis=1)
        # heatmap-like: rows agents (sorted by dominance), cols actions
        order = dom_pct.sort_values(ascending=False).index
        per_pct = per_pct.loc[order]
        im = ax.imshow(per_pct.values, aspect="auto", cmap="Blues",
                       vmin=0, vmax=100)
        ax.set_xticks(range(len(ACTION_ORDER)))
        ax.set_xticklabels(ACTION_ORDER, rotation=45, ha="right", fontsize=6.0)
        ax.set_yticks([])
        ax.set_ylabel(YLABEL_AGENTS_SORTED if mkt.startswith("Tesla") else "")
        ax.set_title(mkt, fontsize=7, color=NEUTRAL_DARK)
        cb = plt.colorbar(im, ax=ax, shrink=0.7, pad=0.02)
        cb.set_label(CB_ACTION_SHARE, fontsize=6.0)
        for aid_pos, aid in enumerate(order):
            for j, act in enumerate(ACTION_ORDER):
                src.append({"market": mkt, "agent_pos": int(aid_pos),
                            "agent_id": int(aid), "action": act,
                            "share_pct": float(per_pct.iloc[aid_pos, j])})
    finalize(fig, OUT_FIG / FIG_DECISION_ACTIONS,
             source_data=pd.DataFrame(src))


# ──────────────────────────────────────────────────────────────────────
# Per-run summary table
# ──────────────────────────────────────────────────────────────────────
def table_summary():
    rows = []
    for suite in ("c5_robotaxi", "c5_ethereum", "c1_robotaxi", "c1_ethereum"):
        for run in (V14 / suite).glob("2026*/"):
            a = load_actions(run)
            n_agents = a["agent_id"].nunique()
            n_ticks = int(a["tick_idx"].max()) + 1
            mix = (a["action_type"].value_counts(normalize=True) * 100).to_dict()
            # belief stats
            beliefs = a[a.action_type == "UPDATE_BELIEF"]
            belief_first = beliefs.groupby("agent_id").first()["price"]
            belief_last = beliefs.groupby("agent_id").last()["price"]
            # average yes_mid path
            mids = (a.dropna(subset=["yes_mid_after"])
                    .groupby("tick_idx").yes_mid_after.last())
            # belief vs price gap
            mean_belief_end = belief_last.mean() if len(belief_last) else float("nan")
            end_price = float(mids.iloc[-1]) if len(mids) else float("nan")
            # consistency
            cr = belief_consistency_for(run)
            rows.append({
                "suite": suite,
                "run": run.name[:35],
                "n_agents": n_agents,
                "n_ticks": n_ticks,
                "belief_updates_per_agent": round(
                    (a.action_type == "UPDATE_BELIEF").sum() / n_agents, 1),
                "mean_initial_belief": round(belief_first.mean(), 3)
                    if len(belief_first) else None,
                "mean_final_belief": round(mean_belief_end, 3),
                "final_market_price": round(end_price, 3),
                "belief_minus_price": round(mean_belief_end - end_price, 3),
                "trades_consistent_pct": round(cr["frac_consistent"] * 100, 1),
                "limit_pct": round(mix.get("LIMIT", 0.0), 1),
                "cancel_pct": round(mix.get("CANCEL", 0.0), 1),
                "hold_pct": round(mix.get("HOLD", 0.0), 1),
                "belief_pct": round(mix.get("UPDATE_BELIEF", 0.0), 1),
            })
    pd.DataFrame(rows).to_csv(OUT_TBL / TBL_DECISION_SUMMARY,
                              index=False)


# ──────────────────────────────────────────────────────────────────────
def main():
    print("belief trajectory …")
    fig_belief()
    print("belief→trade consistency …")
    fig_consistency()
    print("action specialisation …")
    fig_actions()
    print("decision summary table …")
    table_summary()
    print(f"\nfigures → {OUT_FIG}")
    print(f"tables  → {OUT_TBL}")


if __name__ == "__main__":
    main()
