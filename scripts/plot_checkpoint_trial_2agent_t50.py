"""Plot the 2-agent, 50-tick checkpoint trial.

The layout follows the reference-paper habit of linking macro market movement
with micro agent state in compact, lettered panels.

Run:
    uv run python scripts/plot_checkpoint_trial_2agent_t50.py
"""
from __future__ import annotations

import json
import argparse
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
    panel_label,
)


apply_style(font_size=7.1)

ROOT = Path(__file__).resolve().parent.parent
RUN_ROOT = ROOT / "output" / "v14" / "checkpoint_trial"
OUT_FIG = ROOT / "docs" / "v14" / "figures"
FIG_NAME = "试稿_2agent_50tick_checkpoint_trial"

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


def latest_run(run_root: Path = RUN_ROOT) -> Path:
    runs = [
        p for p in run_root.glob("*/")
        if (p / "meta.json").exists()
        and (p / "raw" / "agent_actions.parquet").exists()
    ]
    if not runs:
        raise SystemExit(f"No checkpoint trial run found under {run_root}")
    return max(runs, key=lambda p: p.stat().st_mtime)


def load_run(run_dir: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta = json.loads((run_dir / "meta.json").read_text())
    actions = pd.read_parquet(run_dir / "raw" / "agent_actions.parquet")
    fills = pd.read_parquet(run_dir / "raw" / "agent_fills.parquet")
    summaries = pd.read_json(
        run_dir / "checkpoint" / "tick_summary.jsonl",
        lines=True,
    )
    events_path = run_dir / "checkpoint" / "compact_events.jsonl"
    if events_path.exists() and events_path.stat().st_size > 0:
        events = pd.read_json(events_path, lines=True)
    else:
        events = pd.DataFrame(columns=["tick", "reason", "context_chars"])
    return meta, actions, fills, summaries, events


def parse_beliefs(actions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    belief_rows = actions[actions["action_type"] == "UPDATE_BELIEF"]
    for r in belief_rows.itertuples(index=False):
        try:
            payload = json.loads(r.raw_response)
        except (TypeError, json.JSONDecodeError):
            continue
        belief = payload.get("belief_update", {})
        rows.append({
            "tick_idx": int(r.tick_idx),
            "agent_id": int(r.agent_id),
            "yes_prob": float(belief.get("yes_prob", np.nan)),
            "confidence": float(belief.get("confidence", np.nan)),
        })
    return pd.DataFrame(rows)


def dominant_action(sub: pd.DataFrame) -> str:
    if sub.empty:
        return "HOLD"
    no_belief = sub[sub["action_type"] != "UPDATE_BELIEF"]
    if no_belief.empty:
        return "UPDATE_BELIEF"
    return str(no_belief.iloc[-1]["action_type"])


def action_matrix(actions: pd.DataFrame) -> tuple[list[int], list[int], np.ndarray]:
    agents = sorted(actions["agent_id"].dropna().astype(int).unique())
    ticks = list(range(int(actions["tick_idx"].max()) + 1))
    code = {a: i for i, a in enumerate(ACTION_ORDER)}
    matrix = np.full((len(agents), len(ticks)), code["HOLD"], dtype=float)
    grouped = actions.groupby(["agent_id", "tick_idx"], sort=False)
    for i, aid in enumerate(agents):
        for j, tick in enumerate(ticks):
            key = (aid, tick)
            sub = grouped.get_group(key) if key in grouped.groups else actions.iloc[0:0]
            matrix[i, j] = code.get(dominant_action(sub), code["HOLD"])
    return agents, ticks, matrix


def truth_target(meta: dict) -> tuple[float | None, str]:
    slug = meta.get("config", {}).get("market", {}).get("slug", "")
    resolved = meta.get("priors_summary", {}).get("resolved_yes")
    priors_path = ROOT / f"data/priors_{slug}.json"
    if resolved is None and priors_path.exists():
        priors = json.loads(priors_path.read_text())
        resolved = priors.get("winning_idx")
    if resolved is None:
        return None, "未结算"
    truth = 1.0 if int(resolved) == 1 else 0.0
    return truth, "正确方向：趋近 1.00" if truth == 1.0 else "正确方向：趋近 0.00"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", default=str(RUN_ROOT))
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--figure-name", default=FIG_NAME)
    args = parser.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else latest_run(Path(args.run_root))
    meta, actions, fills, summaries, events = load_run(run_dir)
    beliefs = parse_beliefs(actions)
    agents, ticks, matrix = action_matrix(actions)

    price = (
        actions.dropna(subset=["yes_mid_after"])
        .groupby("tick_idx")["yes_mid_after"]
        .last()
        .reindex(ticks)
        .ffill()
    )
    fill_by_tick = (
        fills.groupby("tick_idx")["notional"].sum().reindex(ticks, fill_value=0.0)
        if not fills.empty else pd.Series(0.0, index=ticks)
    )
    context_tokens = summaries["response_chars"].cumsum() / 4.0
    truth, direction = truth_target(meta)
    language = meta.get("config", {}).get("llm", {}).get("prompt_language", "en")
    title_suffix = "（中文版 prompt）" if language == "zh" else ""

    fig = plt.figure(figsize=fig_size(COL_DOUBLE_MM, 164))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.1, 1.0, 0.85],
                          width_ratios=[1.25, 1.05], hspace=0.52, wspace=0.30)
    ax_price = fig.add_subplot(gs[0, :])
    ax_belief = fig.add_subplot(gs[1, 0], sharex=ax_price)
    ax_actions = fig.add_subplot(gs[1, 1], sharex=ax_price)
    ax_volume = fig.add_subplot(gs[2, 0], sharex=ax_price)
    ax_context = fig.add_subplot(gs[2, 1], sharex=ax_price)

    ax_price.plot(ticks, price, color=BLUE, lw=1.35, marker="o", ms=2.2)
    ax_price.axhline(1.0, color=GREEN_DEEP, ls=":", lw=0.7, alpha=0.65)
    ax_price.axhline(0.5, color=NEUTRAL_MID, ls="--", lw=0.7, alpha=0.60)
    ax_price.axhline(0.0, color=RED, ls=":", lw=0.7, alpha=0.65)
    if truth is not None:
        ax_price.axhline(truth, color=GOLD, lw=1.0, alpha=0.30)
    ax_price.set_ylim(-0.04, 1.04)
    ax_price.set_ylabel("YES 价格")
    ax_price.set_title(
        f"2-agent 50-tick 交易与压缩 checkpoint 试验{title_suffix}",
        color=NEUTRAL_DARK,
    )
    ax_price.text(0.01, 0.90, direction, transform=ax_price.transAxes,
                  ha="left", va="top", fontsize=6.3, color=NEUTRAL_DARK)
    panel_label(ax_price, "a")

    if not beliefs.empty:
        for aid, sub in beliefs.groupby("agent_id"):
            ax_belief.plot(
                sub["tick_idx"], sub["yes_prob"],
                lw=1.0, marker=".", ms=3.0,
                color=BLUE if aid == agents[0] else GREEN_DEEP,
                label=f"Agent {aid} 信念",
            )
            ax_belief.scatter(
                sub["tick_idx"], sub["confidence"],
                s=9, color=NEUTRAL_DARK, alpha=0.20,
            )
    ax_belief.axhline(0.5, color=NEUTRAL_MID, ls="--", lw=0.6, alpha=0.55)
    ax_belief.set_ylim(-0.04, 1.04)
    ax_belief.set_ylabel("信念 / 置信度")
    ax_belief.legend(loc="lower left", fontsize=5.8)
    panel_label(ax_belief, "b")

    cmap = ListedColormap([ACTION_COLORS[a] for a in ACTION_ORDER])
    ax_actions.imshow(
        matrix, aspect="auto", interpolation="nearest",
        cmap=cmap, vmin=-0.5, vmax=len(ACTION_ORDER) - 0.5,
    )
    ax_actions.set_yticks(np.arange(len(agents)))
    ax_actions.set_yticklabels([str(a) for a in agents])
    ax_actions.set_ylabel("智能体")
    ax_actions.set_xlabel("tick")
    for x in np.arange(-0.5, len(ticks), 5):
        ax_actions.axvline(x, color="white", lw=0.35, alpha=0.55)
    handles = [Patch(facecolor=ACTION_COLORS[a], label=ACTION_LABELS[a])
               for a in ACTION_ORDER]
    ax_actions.legend(handles=handles, loc="upper center",
                      bbox_to_anchor=(0.50, -0.22), ncol=3, fontsize=5.4)
    panel_label(ax_actions, "c")

    action_counts = (
        actions[actions["action_type"] != "UPDATE_BELIEF"]
        .groupby(["tick_idx", "action_type"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=ticks, fill_value=0)
    )
    bottom = np.zeros(len(ticks))
    for action in ["HOLD", "LIMIT", "MARKET", "CANCEL", "SPLIT", "MERGE"]:
        vals = action_counts[action].to_numpy() if action in action_counts else bottom * 0
        ax_volume.bar(ticks, vals, bottom=bottom, width=0.82,
                      color=ACTION_COLORS[action], edgecolor="white", linewidth=0.2)
        bottom += vals
    fill_vals = fill_by_tick.to_numpy(dtype=float)
    if fill_vals.max() > 0:
        fill_scaled = fill_vals / fill_vals.max() * max(bottom.max(), 1.0)
    else:
        fill_scaled = fill_vals
    ax_volume.plot(ticks, fill_scaled, color=NEUTRAL_DARK,
                   lw=1.0, marker=".", ms=2.8)
    ax_volume.set_ylabel("交易动作数")
    ax_volume.set_xlabel("tick")
    panel_label(ax_volume, "d")

    ax_context.plot(
        summaries["tick"], context_tokens,
        color=VIOLET, lw=1.1, marker=".", ms=2.8,
    )
    if not events.empty:
        y_max = max(context_tokens.max(), 1)
        for r in events.itertuples(index=False):
            ax_context.axvline(int(r.tick), color=GOLD, lw=0.75, alpha=0.55)
        ax_context.text(
            0.02, 0.94, "金色竖线 = handoff 写入",
            transform=ax_context.transAxes,
            ha="left", va="top", fontsize=5.8, color=NEUTRAL_DARK,
        )
    ax_context.set_ylabel("响应 token 估算")
    ax_context.set_xlabel("tick")
    panel_label(ax_context, "e")

    for ax in [ax_price, ax_belief, ax_volume, ax_context]:
        ax.set_xlim(-0.5, max(ticks) + 0.5)
        ax.set_xticks(np.arange(0, max(ticks) + 1, 5))

    source = summaries.copy()
    source["run_dir"] = run_dir.name
    source["slug"] = meta["config"]["market"]["slug"]
    source["price"] = source["tick"].map(price.to_dict())

    finalize(
        fig,
        OUT_FIG / args.figure_name,
        source_data=source,
        formats=("png", "svg", "pdf"),
        pad=0.45,
    )
    print(OUT_FIG / f"{args.figure_name}.png")
    print(OUT_FIG / "data" / f"{args.figure_name}.csv")
    print(run_dir / "checkpoint" / "handoff.md")


if __name__ == "__main__":
    main()
