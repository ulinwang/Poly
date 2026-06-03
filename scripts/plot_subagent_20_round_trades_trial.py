"""Trial figure: 20-round subagent trading process.

The figure uses one representative v14 run with 20 agents and 20 rounds. It
shows market price, each agent's dominant action per round, fill participation,
and round-level action composition.

Run:
    uv run python scripts/plot_subagent_20_round_trades_trial.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

from _thesis_style import (
    BLUE,
    BLUE_LIGHT,
    COL_DOUBLE_MM,
    GOLD,
    GREEN_DEEP,
    NEUTRAL_DARK,
    NEUTRAL_LIGHT,
    NEUTRAL_MID,
    RED,
    TEAL,
    VIOLET,
    apply_style,
    fig_size,
    finalize,
)


apply_style(font_size=7.2)

ROOT = Path(__file__).resolve().parent.parent
OUT_FIG = ROOT / "docs" / "v14" / "figures"
RUN_DIR = (
    ROOT
    / "output"
    / "v14"
    / "c1_robotaxi"
    / "20260522T192945-c1_robotaxi_n20_s0-d94a3981-c65ed02b"
)
FIG_NAME = "试稿_subagent_20轮交易过程图"


ACTION_PRIORITY = {
    "MARKET": 70,
    "LIMIT": 60,
    "CANCEL": 50,
    "SPLIT": 40,
    "MERGE": 40,
    "HOLD": 30,
    "UPDATE_BELIEF": 20,
}

ACTION_ORDER = [
    "UPDATE_BELIEF",
    "HOLD",
    "LIMIT",
    "MARKET",
    "CANCEL",
    "SPLIT",
    "MERGE",
]

ACTION_LABELS = {
    "UPDATE_BELIEF": "信念更新",
    "HOLD": "持有",
    "LIMIT": "限价挂单",
    "MARKET": "市价成交",
    "CANCEL": "撤单",
    "SPLIT": "拆分",
    "MERGE": "合并",
}

ACTION_COLORS = {
    "UPDATE_BELIEF": NEUTRAL_LIGHT,
    "HOLD": NEUTRAL_MID,
    "LIMIT": BLUE,
    "MARKET": GREEN_DEEP,
    "CANCEL": RED,
    "SPLIT": TEAL,
    "MERGE": VIOLET,
}


def dominant_action(sub: pd.DataFrame) -> str:
    if sub.empty:
        return "HOLD"
    ordered = sorted(
        sub["action_type"].fillna("HOLD").tolist(),
        key=lambda x: ACTION_PRIORITY.get(str(x), 0),
        reverse=True,
    )
    return str(ordered[0])


def load_run() -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta = json.loads((RUN_DIR / "meta.json").read_text())
    actions = pd.read_parquet(RUN_DIR / "raw" / "agent_actions.parquet")
    fills = pd.read_parquet(RUN_DIR / "raw" / "agent_fills.parquet")
    positions = pd.read_parquet(RUN_DIR / "raw" / "agent_positions.parquet")
    return meta, actions, fills, positions


def build_agent_round_table(actions: pd.DataFrame, fills: pd.DataFrame) -> pd.DataFrame:
    agents = sorted(actions["agent_id"].dropna().astype(int).unique())
    ticks = list(range(int(actions["tick_idx"].max()) + 1))
    fill_rows = []
    for r in fills.itertuples(index=False):
        for role, aid in (("maker", r.maker_agent_id), ("taker", r.taker_agent_id)):
            if int(aid) == 999999:
                continue
            fill_rows.append(
                {
                    "agent_id": int(aid),
                    "tick_idx": int(r.tick_idx),
                    "fill_role": role,
                    "fill_notional": float(r.notional),
                }
            )
    fill_df = pd.DataFrame(fill_rows)
    fill_sum = (
        fill_df.groupby(["agent_id", "tick_idx"])["fill_notional"].sum()
        if not fill_df.empty
        else pd.Series(dtype=float)
    )

    rows = []
    grouped = actions.groupby(["agent_id", "tick_idx"], sort=False)
    for aid in agents:
        for tick in ticks:
            key = (aid, tick)
            sub = grouped.get_group(key) if key in grouped.groups else actions.iloc[0:0]
            action = dominant_action(sub)
            size_usd = float(sub["size_usd"].fillna(0).sum()) if not sub.empty else 0.0
            n_actions = int(len(sub))
            fill_notional = float(fill_sum.get(key, 0.0))
            rows.append(
                {
                    "agent_id": aid,
                    "tick_idx": tick,
                    "dominant_action": action,
                    "action_label": ACTION_LABELS.get(action, action),
                    "n_actions": n_actions,
                    "order_size_usd": size_usd,
                    "fill_notional": fill_notional,
                    "had_fill": fill_notional > 0,
                }
            )
    return pd.DataFrame(rows)


def plot() -> None:
    meta, actions, fills, positions = load_run()
    table = build_agent_round_table(actions, fills)
    agents = sorted(table["agent_id"].unique())
    ticks = sorted(table["tick_idx"].unique())
    action_to_code = {a: i for i, a in enumerate(ACTION_ORDER)}

    matrix = np.full((len(agents), len(ticks)), np.nan)
    fill_matrix = np.zeros_like(matrix, dtype=float)
    for r in table.itertuples(index=False):
        i = agents.index(r.agent_id)
        j = ticks.index(r.tick_idx)
        matrix[i, j] = action_to_code.get(r.dominant_action, 0)
        fill_matrix[i, j] = r.fill_notional

    mids = (
        actions.dropna(subset=["yes_mid_after"])
        .groupby("tick_idx")["yes_mid_after"]
        .last()
        .reindex(ticks)
        .ffill()
    )
    action_counts = (
        table.groupby(["tick_idx", "dominant_action"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=ticks, columns=ACTION_ORDER, fill_value=0)
    )
    fill_by_tick = fills.groupby("tick_idx")["notional"].sum().reindex(ticks, fill_value=0.0)

    fig = plt.figure(figsize=fig_size(COL_DOUBLE_MM, 150))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.05, 3.2, 1.35], hspace=0.22)
    ax_price = fig.add_subplot(gs[0, 0])
    ax_heat = fig.add_subplot(gs[1, 0])
    ax_counts = fig.add_subplot(gs[2, 0], sharex=ax_heat)

    ax_price.plot(ticks, mids, color=BLUE, lw=1.4, marker="o", ms=2.4)
    ax_price.axhline(1.0, color=GREEN_DEEP, ls=":", lw=0.7, alpha=0.7)
    ax_price.axhline(0.5, color=NEUTRAL_MID, ls="--", lw=0.7, alpha=0.65)
    ax_price.axhline(0.0, color=RED, ls=":", lw=0.7, alpha=0.7)
    ax_price.set_ylim(-0.04, 1.04)
    ax_price.set_ylabel("YES 价格")
    ax_price.set_title(
        "20 轮 subagent 交易过程（Robotaxi, n=20, seed=0）",
        color=NEUTRAL_DARK,
    )
    ax_price.text(
        0.01,
        0.90,
        "上：市场价格；中：每个智能体每轮主导动作（白点=该轮有成交）；下：动作结构与成交额",
        transform=ax_price.transAxes,
        ha="left",
        va="top",
        fontsize=6.2,
        color=NEUTRAL_DARK,
    )

    cmap = ListedColormap([ACTION_COLORS[a] for a in ACTION_ORDER])
    ax_heat.imshow(
        matrix,
        aspect="auto",
        interpolation="nearest",
        cmap=cmap,
        vmin=-0.5,
        vmax=len(ACTION_ORDER) - 0.5,
    )
    fill_y, fill_x = np.where(fill_matrix > 0)
    fill_size = 12 + np.clip(fill_matrix[fill_y, fill_x], 0, 80) * 0.55
    ax_heat.scatter(
        fill_x,
        fill_y,
        s=fill_size,
        facecolors="white",
        edgecolors=NEUTRAL_DARK,
        linewidths=0.35,
        alpha=0.9,
        label="发生成交",
    )
    ax_heat.set_ylabel("智能体 ID")
    ax_heat.set_yticks(np.arange(len(agents)))
    ax_heat.set_yticklabels([str(a) for a in agents], fontsize=5.8)
    ax_heat.set_xticks(np.arange(len(ticks)))
    ax_heat.set_xticklabels([str(t + 1) for t in ticks], fontsize=5.8)
    ax_heat.set_xlim(-0.5, len(ticks) - 0.5)
    ax_heat.set_xlabel("交易轮次")
    for x in np.arange(-0.5, len(ticks), 1):
        ax_heat.axvline(x, color="white", lw=0.25, alpha=0.45)
    for y in np.arange(-0.5, len(agents), 1):
        ax_heat.axhline(y, color="white", lw=0.25, alpha=0.45)

    bottom = np.zeros(len(ticks))
    for action in ACTION_ORDER:
        vals = action_counts[action].to_numpy()
        ax_counts.bar(
            ticks,
            vals,
            bottom=bottom,
            color=ACTION_COLORS[action],
            edgecolor="white",
            linewidth=0.25,
            width=0.82,
            label=ACTION_LABELS[action],
        )
        bottom += vals
    ax_counts.set_ylabel("智能体数")
    ax_counts.set_xlabel("交易轮次")
    ax_counts.set_xticks(ticks)
    ax_counts.set_xticklabels([str(t + 1) for t in ticks], fontsize=5.8)

    ax_fill = ax_counts.twinx()
    ax_fill.plot(
        ticks,
        fill_by_tick.to_numpy(),
        color=NEUTRAL_DARK,
        lw=1.1,
        marker=".",
        ms=3,
        label="成交额",
    )
    ax_fill.set_ylabel("成交额")
    ax_fill.spines["right"].set_visible(True)

    action_handles = [
        Patch(facecolor=ACTION_COLORS[a], label=ACTION_LABELS[a])
        for a in ACTION_ORDER
    ]
    ax_heat.legend(
        handles=action_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=7,
        fontsize=5.8,
    )
    ax_counts.legend(loc="upper left", ncol=4, fontsize=5.8)
    ax_fill.legend(loc="upper right", fontsize=5.8)

    source = table.merge(
        positions[["tick_idx", "agent_id", "yes_shares", "no_shares", "cash"]],
        on=["tick_idx", "agent_id"],
        how="left",
    )
    source["yes_mid_after"] = source["tick_idx"].map(mids.to_dict())
    source["run_dir"] = RUN_DIR.name
    source["slug"] = meta["config"]["market"]["slug"]

    finalize(
        fig,
        OUT_FIG / FIG_NAME,
        source_data=source,
        formats=("png", "svg", "pdf"),
        pad=0.25,
    )
    print(OUT_FIG / f"{FIG_NAME}.png")
    print(OUT_FIG / "data" / f"{FIG_NAME}.csv")


if __name__ == "__main__":
    plot()
