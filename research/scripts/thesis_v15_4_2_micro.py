"""v15 thesis 4.2 micro-level (per-agent) figures + tables.

Covers:
  4.2.1 典型 agent 信念/交易/损益时间线
  4.2.2 智能体数量与决策轮数扩展下的执行率行为
  4.2.3 规模轮数微观汇总指标
  4.2.4 微观消融行为 (c4/c5/c6) — baseline vs ablation action mix per module

Run standalone or via ``scripts/thesis_v15_analysis.py``.
"""
from __future__ import annotations

import math
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _thesis_v15_common import (
    BLUE, GREEN, RED, GOLD, TEAL, VIOLET,
    NEUTRAL_MID, NEUTRAL_DARK,
    BASE_MARKETS, MARKET_LABEL, MARKET_COLOR,
    ACTION_ORDER, ACTION_COLOR, ABLATION_MODULES,
    TRADING_ACTIONS, ACTIVE_TRADE_ACTIONS,
    COL_DOUBLE_MM,
    OUT_TBL, OUT_ANALYSIS,
    config_name, latest_runs_of, grouped,
    market_title_for,
    metrics, integer_xaxis,
    load_actions, load_positions, yes_mid_path,
    cumulative_trade_map, micro_trade_count_behavior_path,
    finalize_v15, save_metric_table,
    fig_size, fig_size_vstack, panel_label,
)


ACTION_LABEL_ZH = {
    "LIMIT": "限价单",
    "MARKET": "市价单",
    "CANCEL": "撤单",
    "HOLD": "持有",
    "SPLIT": "拆分",
    "MERGE": "合并",
}


# === 4.2.1 representative agents =============================================
def choose_representative_run() -> Path | None:
    candidates = latest_runs_of("c1_ethereum")
    for run in candidates:
        if "_n20_" in config_name(run):
            return run
    return candidates[0] if candidates else None


def selected_agents(actions: pd.DataFrame, positions: pd.DataFrame, n: int = 3) -> list[int]:
    final_pos = positions.sort_values("tick_idx").groupby("agent_id").tail(1).copy()
    final_pos["pnl"] = final_pos["realized_pnl"].astype(float) + final_pos["unrealized_pnl"].astype(float)
    trade_counts = actions[actions["action_type"].isin(ACTIVE_TRADE_ACTIONS)].groupby("agent_id").size()
    score = final_pos.set_index("agent_id")["pnl"].abs().rank(pct=True).fillna(0)
    score = score.add(trade_counts.rank(pct=True).fillna(0), fill_value=0)
    return [int(x) for x in score.sort_values(ascending=False).head(n).index]


def truncate_text(s: object, width: int = 180) -> str:
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return ""
    return textwrap.shorten(str(s).replace("\n", " "), width=width, placeholder="...")


def representative_agent_table(run: Path, agents: list[int]) -> pd.DataFrame:
    actions = load_actions(run).sort_values(["tick_idx", "agent_id"])
    positions = load_positions(run)
    pnl = positions.copy()
    pnl["pnl"] = pnl["realized_pnl"].astype(float) + pnl["unrealized_pnl"].astype(float)
    pnl_map = pnl.set_index(["tick_idx", "agent_id"])["pnl"].to_dict()
    rows = []
    for aid in agents:
        sub = actions[actions["agent_id"] == aid]
        for tick, g in sub.groupby("tick_idx"):
            belief = g[g["action_type"] == "UPDATE_BELIEF"].tail(1)
            decision = g[g["action_type"].isin(TRADING_ACTIONS)].tail(1)
            b = belief.iloc[0] if len(belief) else None
            d = decision.iloc[0] if len(decision) else None
            belief_prob = float(b["price"]) if b is not None and pd.notna(b["price"]) else float("nan")
            mid = float(d["yes_mid_before"]) if d is not None and pd.notna(d["yes_mid_before"]) else float("nan")
            if math.isnan(belief_prob) or math.isnan(mid):
                direction = ""
            elif belief_prob > mid + 0.02:
                direction = "above_market"
            elif belief_prob < mid - 0.02:
                direction = "below_market"
            else:
                direction = "near_market"
            rows.append({
                "tick": int(tick),
                "agent_id": int(aid),
                "belief_yes_prob": round(belief_prob, 4) if not math.isnan(belief_prob) else None,
                "belief_direction": direction,
                "belief_summary": truncate_text(b["reasoning"] if b is not None else ""),
                "action": str(d["action_type"]) if d is not None else "",
                "outcome": str(d["outcome"]) if d is not None and pd.notna(d["outcome"]) else "",
                "side": str(d["side"]) if d is not None and pd.notna(d["side"]) else "",
                "price": float(d["price"]) if d is not None and pd.notna(d["price"]) else None,
                "size": float(d["size_usd"]) if d is not None and pd.notna(d["size_usd"]) else None,
                "filled": int(d["n_fills"]) if d is not None and pd.notna(d["n_fills"]) else 0,
                "pnl": round(float(pnl_map.get((tick, aid), float("nan"))), 4),
                "trade_reasoning": truncate_text(d["reasoning"] if d is not None else ""),
            })
    return pd.DataFrame(rows)


def write_agent_markdown(table: pd.DataFrame) -> None:
    lines = [
        "# 4.2.1 典型 agent 思考过程摘录",
        "",
        "说明：belief 是一段自然语言判断，表中的 belief_yes_prob 只是模型通过 UPDATE_BELIEF 工具声明的 YES 概率，用于绘图和一致性检验；解释时应以 belief_summary 与后续交易动作的匹配关系为主。",
        "",
    ]
    for aid, sub in table.groupby("agent_id"):
        lines.append(f"## Agent {aid}")
        picks = pd.concat([sub.head(2), sub.iloc[max(len(sub)//2-1, 0):len(sub)//2+1], sub.tail(2)]).drop_duplicates("tick")
        for _, row in picks.iterrows():
            lines.append(
                f"- tick {row['tick']}: belief={row['belief_direction']} "
                f"(p={row['belief_yes_prob']}), action={row['action']} "
                f"{row['side']} {row['outcome']} @ {row['price']}, "
                f"filled={row['filled']}, 损益={row['pnl']}。"
            )
            if row["belief_summary"]:
                lines.append(f"  - belief text: {row['belief_summary']}")
            if row["trade_reasoning"]:
                lines.append(f"  - action text: {row['trade_reasoning']}")
        lines.append("")
    (OUT_ANALYSIS / "4_2_1_典型agent思考过程.md").write_text("\n".join(lines))


def fig_micro_behavior() -> None:
    run = choose_representative_run()
    if run is None:
        return
    actions = load_actions(run)
    positions = load_positions(run)
    agents = selected_agents(actions, positions, 3)
    mids = yes_mid_path(actions)
    cum_trade_by_tick = cumulative_trade_map(run)
    table = representative_agent_table(run, agents)
    table.to_csv(OUT_TBL / "表_4_2_1_典型agent信念交易损益时间线.csv", index=False)
    write_agent_markdown(table)

    fig, axes = plt.subplots(3, 1, figsize=fig_size_vstack(3, panel_mm=60))
    src = []

    ax = axes[0]
    ax.set_title("典型智能体信念与市场价格", fontsize=7.5)
    mid_x = [cum_trade_by_tick.get(int(t), 0.0) for t in mids.index]
    ax.plot(mid_x, mids.to_numpy(), color=NEUTRAL_DARK, lw=1.3, label="模拟市场价格")
    for aid, color in zip(agents, [BLUE, GREEN, RED]):
        b = actions[(actions["agent_id"] == aid) & (actions["action_type"] == "UPDATE_BELIEF")]
        bx = [cum_trade_by_tick.get(int(t), 0.0) for t in b["tick_idx"]]
        ax.plot(bx, b["price"], "o-", color=color, lw=0.9, label=f"agent {aid} 信念")
        src.extend(
            {"panel": "belief", "agent_id": aid, "tick": int(t), "cum_trades": float(x), "value": float(v)}
            for t, x, v in zip(b["tick_idx"], bx, b["price"])
        )
    ax.set_ylabel("YES 概率")
    ax.set_ylim(-0.03, 1.03)
    ax.legend(loc="best", fontsize=6.0)
    integer_xaxis(ax)
    panel_label(ax, "a")

    ax = axes[1]
    ax.set_title("交易动作组成", fontsize=7.5)
    decision = actions[actions["action_type"].isin(TRADING_ACTIONS)]
    mix_counts = decision["action_type"].value_counts().reindex(ACTION_ORDER, fill_value=0).astype(float)
    total_actions = max(float(mix_counts.sum()), 1.0)
    mix_pct = mix_counts / total_actions * 100.0
    x = np.arange(len(ACTION_ORDER), dtype=float)
    for act in ACTION_ORDER:
        idx = ACTION_ORDER.index(act)
        val = float(mix_pct[act])
        ax.bar(x[idx], val, width=0.7, color=ACTION_COLOR[act], label=ACTION_LABEL_ZH.get(act, act))
        if val >= 2:
            ax.text(x[idx], val + 1.2, f"{val:.0f}%", ha="center", va="bottom", fontsize=6.0)
    ax.set_ylabel("动作占比 %")
    ax.set_xticks(x)
    ax.set_xticklabels([ACTION_LABEL_ZH.get(act, act) for act in ACTION_ORDER], rotation=25, ha="right", fontsize=5.8)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=5.8)
    ax.set_ylim(0, max(100.0, float(mix_pct.max()) * 1.18))
    panel_label(ax, "b")

    ax = axes[2]
    ax.set_title("典型智能体损益变化", fontsize=7.5)
    p = positions.copy()
    p["pnl"] = p["realized_pnl"].astype(float) + p["unrealized_pnl"].astype(float)
    for aid, color in zip(agents, [BLUE, GREEN, RED]):
        sub = p[p["agent_id"] == aid].sort_values("tick_idx")
        px = [cum_trade_by_tick.get(int(t), 0.0) for t in sub["tick_idx"]]
        ax.plot(px, sub["pnl"], "o-", color=color, lw=0.9, label=f"agent {aid}")
        src.extend(
            {"panel": "损益", "agent_id": aid, "tick": int(t), "cum_trades": float(x), "value": float(v)}
            for t, x, v in zip(sub["tick_idx"], px, sub["pnl"])
        )
    ax.axhline(0, color=NEUTRAL_MID, ls=":", lw=0.8)
    ax.set_xlabel("累积成交笔数")
    ax.set_ylabel("损益")
    ax.legend(loc="best", fontsize=6.0)
    integer_xaxis(ax)
    panel_label(ax, "c")
    finalize_v15(fig, "4-2-1_微观_典型agent图", pd.DataFrame(src))


def pnl_divergence_path(run: Path) -> pd.DataFrame:
    """Aggregate per-agent PnL change into distribution paths over trades.

    We subtract each agent's first observed PnL so the figure emphasizes
    divergence generated during the simulated trading process instead of
    initial inventory valuation differences.
    """
    positions = load_positions(run).copy()
    if positions.empty:
        return pd.DataFrame()
    positions["pnl"] = positions["realized_pnl"].astype(float) + positions["unrealized_pnl"].astype(float)
    initial_pnl = positions.sort_values("tick_idx").groupby("agent_id").first()["pnl"]
    positions["pnl_delta"] = positions["pnl"] - positions["agent_id"].map(initial_pnl)
    cum_trade_by_tick = cumulative_trade_map(run)
    rows: list[dict] = []
    for tick, grp in positions.sort_values(["tick_idx", "agent_id"]).groupby("tick_idx"):
        pnl = grp["pnl_delta"].astype(float).sort_values()
        if pnl.empty:
            continue
        n_tail = max(1, int(math.ceil(len(pnl) * 0.2)))
        rows.append({
            "tick": int(tick),
            "累积成交笔数": float(cum_trade_by_tick.get(int(tick), 0.0)),
            "底部20%平均损益增量": float(pnl.head(n_tail).mean()),
            "中位数损益增量": float(pnl.median()),
            "顶部20%平均损益增量": float(pnl.tail(n_tail).mean()),
            "p10损益增量": float(pnl.quantile(0.10)),
            "p25损益增量": float(pnl.quantile(0.25)),
            "p75损益增量": float(pnl.quantile(0.75)),
            "p90损益增量": float(pnl.quantile(0.90)),
            "p90-p10损益增量差": float(pnl.quantile(0.90) - pnl.quantile(0.10)),
        })
    return pd.DataFrame(rows)


def fig_micro_pnl_divergence() -> None:
    """4.2.1 supplement: visualize Matthew-effect-like PnL divergence."""
    run = choose_representative_run()
    if run is None:
        return
    path = pnl_divergence_path(run)
    if path.empty:
        return

    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=58), sharex=True)
    x = path["累积成交笔数"]

    ax = axes[0]
    ax.set_title("智能体损益增量分化路径", fontsize=7.5)
    ax.fill_between(x, path["p25损益增量"], path["p75损益增量"], color=BLUE, alpha=0.12, label="中间50%区间")
    ax.plot(x, path["顶部20%平均损益增量"], "o-", color=BLUE, lw=1.2, label="顶部20%平均损益增量")
    ax.plot(x, path["中位数损益增量"], "o-", color=NEUTRAL_DARK, lw=1.0, label="中位数损益增量")
    ax.plot(x, path["底部20%平均损益增量"], "o-", color=RED, lw=1.2, label="底部20%平均损益增量")
    ax.axhline(0, color=NEUTRAL_MID, ls=":", lw=0.8)
    ax.set_ylabel("损益增量")
    ax.legend(loc="best", fontsize=5.8, ncol=2)
    integer_xaxis(ax)
    panel_label(ax, "a")

    ax = axes[1]
    ax.set_title("损益增量分化幅度", fontsize=7.5)
    ax.plot(x, path["p90-p10损益增量差"], "o-", color=VIOLET, lw=1.2, label="p90-p10损益增量差")
    ax.set_xlabel("累积成交笔数")
    ax.set_ylabel("p90-p10 损益增量差")
    ax.legend(loc="best", fontsize=6.0)
    integer_xaxis(ax)
    panel_label(ax, "b")

    finalize_v15(fig, "4-2-1_微观_损益分化图", path)


# === 4.2.2 / 4.2.3 micro scale + tick =========================================
def fig_micro_scale_tick() -> None:
    rows = []
    for mkt in BASE_MARKETS:
        for run in latest_runs_of(f"c1_{mkt}") + latest_runs_of(f"c3_{mkt}"):
            rows.append(metrics(run))
    if not rows:
        return
    df = pd.DataFrame([{k: v for k, v in r.items() if k not in ("run", "mids", "action_mix")} for r in rows])
    df.to_csv(OUT_TBL / "表_4_2_2_4_2_3_规模轮数微观指标.csv", index=False)

    fig, axes = plt.subplots(4, 1, figsize=fig_size_vstack(4, panel_mm=52))
    src = []
    ns = [10, 20, 50, 100]
    ts = [10, 20, 50, 100]
    colors = [BLUE, GREEN, GOLD, RED]
    for idx, mkt in enumerate(BASE_MARKETS):
        ax = axes[idx]
        ax.set_title(f"规模扩展·{MARKET_LABEL[mkt]}", fontsize=7.5)
        by_n = grouped(f"c1_{mkt}", r"_n(\d+)_")
        for n, color in zip(ns, colors):
            rs = by_n.get(str(n), [])
            if not rs:
                continue
            r = rs[-1]
            path = micro_trade_count_behavior_path(r, f"n={n}")
            if path.empty:
                continue
            path["experiment"] = "scale"
            src.extend(path.to_dict("records"))
            ax.plot(path["cum_trades"], path["execution_rate"], "o-", color=color, lw=0.9, label=f"n={n}")
        ax.set_xlabel("累积成交笔数")
        ax.set_ylabel("累积主动交易成交率")
        ax.set_ylim(bottom=-0.02)
        ax.legend(loc="best", fontsize=5.8, ncol=2)
        integer_xaxis(ax)
        panel_label(ax, chr(ord("a") + idx))

    for idx, mkt in enumerate(BASE_MARKETS, start=2):
        ax = axes[idx]
        ax.set_title(f"轮数扩展·{MARKET_LABEL[mkt]}", fontsize=7.5)
        by_t = grouped(f"c3_{mkt}", r"_t(\d+)_")
        for t, color in zip(ts, colors):
            rs = by_t.get(str(t), [])
            if not rs:
                continue
            r = rs[-1]
            path = micro_trade_count_behavior_path(r, f"{t}轮")
            if path.empty:
                continue
            path["experiment"] = "tick_horizon"
            src.extend(path.to_dict("records"))
            ax.plot(path["cum_trades"], path["execution_rate"], "o-", color=color, lw=0.9, label=f"{t}轮")
        ax.set_xlabel("累积成交笔数")
        ax.set_ylabel("累积主动交易成交率")
        ax.set_ylim(bottom=-0.02)
        ax.legend(loc="best", fontsize=5.8, ncol=2)
        integer_xaxis(ax)
        panel_label(ax, chr(ord("a") + idx))

    finalize_v15(fig, "4-2-2_微观_规模轮数交易行为图", pd.DataFrame(src))

    metric_specs = [
        ("active_trade_fill_rate", "主动交易成交率"),
        ("pnl_std", "损益标准差"),
        ("cancel_per_fill", "撤单成交比"),
    ]
    fig, axes = plt.subplots(3, 2, figsize=fig_size(COL_DOUBLE_MM, 142), sharex=False, sharey=False)
    for row_idx, (metric_key, metric_label) in enumerate(metric_specs):
        for col_idx, (cfg_token, x_col, x_label, title) in enumerate([
            ("_n", "n_agents", "智能体数量", "智能体数量扩展"),
            ("_t", "n_ticks", "决策轮数", "决策轮数扩展"),
        ]):
            ax = axes[row_idx, col_idx]
            sub_all = df[df["config"].str.contains(cfg_token)].copy()
            settings = sorted(sub_all[x_col].dropna().astype(int).unique())
            x = np.arange(len(settings), dtype=float)
            width = 0.34
            for mkt_idx, mkt in enumerate(BASE_MARKETS):
                sub = df[
                    (df["config"].str.contains(cfg_token))
                    & (df["market_key"] == mkt)
                ].sort_values(x_col).set_index(x_col)
                if sub.empty:
                    continue
                vals = [float(sub.loc[s, metric_key]) if s in sub.index else np.nan for s in settings]
                offset = (mkt_idx - (len(BASE_MARKETS) - 1) / 2) * width
                bars = ax.bar(
                    x + offset, vals, width=width,
                    color=MARKET_COLOR[mkt], alpha=0.9,
                    label=MARKET_LABEL[mkt],
                )
                for bar, val in zip(bars, vals):
                    if not np.isfinite(val):
                        continue
                    label = f"{val:.2f}" if metric_key != "pnl_std" else f"{val:.0f}"
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height(),
                        label,
                        ha="center",
                        va="bottom",
                        fontsize=5.2,
                    )
            if row_idx == 0:
                ax.set_title(title, fontsize=7.5)
            if col_idx == 0:
                ax.set_ylabel(metric_label)
            if row_idx == len(metric_specs) - 1:
                ax.set_xlabel(x_label)
            ax.set_xticks(x)
            ax.set_xticklabels([str(s) for s in settings])
            ax.set_ylim(bottom=0)
            y_max = max(
                [p.get_height() for p in ax.patches if np.isfinite(p.get_height())] or [1.0]
            )
            ax.set_ylim(0, y_max * 1.18 if y_max > 0 else 1.0)
            panel_label(ax, chr(ord("a") + row_idx * 2 + col_idx))
    handles, labels = axes[0, 0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper center", ncol=2, fontsize=6.2, bbox_to_anchor=(0.5, 1.02))
    finalize_v15(fig, "4-2-3_微观_规模轮数汇总图", df)


def _wallet_pnl_distribution(run: Path, experiment: str, setting_label: str) -> pd.DataFrame:
    positions = load_positions(run)
    if positions.empty:
        return pd.DataFrame()
    final_pos = positions.sort_values("tick_idx").groupby("agent_id").tail(1).copy()
    final_pos["final_pnl"] = (
        final_pos["realized_pnl"].astype(float)
        + final_pos["unrealized_pnl"].astype(float)
    )
    final_pos = final_pos.sort_values("final_pnl").reset_index(drop=True)
    n = len(final_pos)
    if n <= 1:
        pct = np.array([50.0])
    else:
        pct = np.linspace(0.0, 100.0, n)
    meta = metrics(run)
    return pd.DataFrame({
        "experiment": experiment,
        "series": setting_label,
        "config": meta["config"],
        "market": meta["market_key"],
        "market_title": MARKET_LABEL.get(meta["market_key"], meta["market_key"]),
        "agent_id": final_pos["agent_id"].astype(int).to_numpy(),
        "wallet_percentile": pct,
        "final_pnl": final_pos["final_pnl"].astype(float).to_numpy(),
    })


def _count_scaled_kde(values: np.ndarray, bins: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return a smooth Gaussian KDE for final wallet PnL values."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return np.array([]), np.array([])
    lo, hi = float(bins[0]), float(bins[-1])
    if not math.isfinite(lo) or not math.isfinite(hi) or lo == hi:
        lo, hi = float(values.min() - 1.0), float(values.max() + 1.0)
    x_grid = np.linspace(lo, hi, 160)
    std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    if std <= 1e-9:
        width = max(abs(float(values.mean())) * 0.02, 1.0)
        center = float(values.mean())
        y = np.exp(-0.5 * ((x_grid - center) / width) ** 2) / (width * math.sqrt(2 * math.pi))
    else:
        bandwidth = 1.06 * std * (len(values) ** (-1 / 5))
        bandwidth = max(bandwidth, (hi - lo) / 80.0, 1e-6)
        z = (x_grid[:, None] - values[None, :]) / bandwidth
        y = np.exp(-0.5 * z**2).mean(axis=1) / (bandwidth * math.sqrt(2 * math.pi))
    return x_grid, y


def _draw_wallet_distribution_panel(
    ax,
    series: list[tuple[pd.DataFrame, str, str]],
    title: str,
    panel: str,
) -> list[pd.DataFrame]:
    """Draw one final-PnL distribution panel and return source frames."""
    non_empty = [(df, label, color) for df, label, color in series if not df.empty]
    if not non_empty:
        ax.set_axis_off()
        return []
    panel_values = pd.concat([df for df, _, _ in non_empty], ignore_index=True)["final_pnl"].astype(float)
    lo, hi = float(panel_values.min()), float(panel_values.max())
    if lo == hi:
        lo, hi = lo - 1.0, hi + 1.0
    pad = max((hi - lo) * 0.04, 1.0)
    bins = np.linspace(lo - pad, hi + pad, 15)
    src_frames: list[pd.DataFrame] = []
    for dist, label, color in non_empty:
        src_frames.append(dist)
        values = dist["final_pnl"].astype(float).to_numpy()
        kde_x, kde_y = _count_scaled_kde(values, bins)
        if len(kde_x):
            ax.plot(kde_x, kde_y, color=color, lw=1.35, label=label)
            ax.fill_between(kde_x, 0, kde_y, color=color, alpha=0.06)
    ax.axvline(0, color=NEUTRAL_MID, ls=":", lw=0.8)
    ax.set_title(title, fontsize=7.2)
    ax.set_xlabel("最终损益")
    ax.set_ylabel("钱包密度")
    ax.legend(loc="best", fontsize=5.8, ncol=2)
    panel_label(ax, panel)
    return src_frames


def _run_dist(run: Path, experiment: str, label: str) -> pd.DataFrame:
    return _wallet_pnl_distribution(run, experiment, label)


def fig_micro_wallet_pnl_scale_distribution() -> None:
    panels = []
    settings = [10, 20, 50, 100]
    colors = [BLUE, GREEN, GOLD, RED]
    for mkt in BASE_MARKETS:
        by_n = grouped(f"c1_{mkt}", r"_n(\d+)_")
        series = []
        for n, color in zip(settings, colors):
            runs = by_n.get(str(n), [])
            if runs:
                series.append((_run_dist(runs[-1]["run"], "scale", f"n={n}"), f"n={n}", color))
        panels.append((f"智能体数量扩展·{MARKET_LABEL[mkt]}", series))
    fig, axes = plt.subplots(1, 2, figsize=fig_size(COL_DOUBLE_MM, 62), sharex=False, sharey=False)
    src_frames = []
    for idx, (title, series) in enumerate(panels):
        src_frames.extend(_draw_wallet_distribution_panel(axes[idx], series, title, chr(ord("a") + idx)))
    src = pd.concat(src_frames, ignore_index=True) if src_frames else pd.DataFrame()
    finalize_v15(fig, "4-2-2_微观_损益分布_规模扩展", src)


def fig_micro_wallet_pnl_tick_distribution() -> None:
    panels = []
    settings = [10, 20, 50, 100]
    colors = [BLUE, GREEN, GOLD, RED]
    for mkt in BASE_MARKETS:
        by_t = grouped(f"c3_{mkt}", r"_t(\d+)_")
        series = []
        for t, color in zip(settings, colors):
            runs = by_t.get(str(t), [])
            if runs:
                series.append((_run_dist(runs[-1]["run"], "tick_horizon", f"{t}轮"), f"{t}轮", color))
        panels.append((f"决策轮数扩展·{MARKET_LABEL[mkt]}", series))
    fig, axes = plt.subplots(1, 2, figsize=fig_size(COL_DOUBLE_MM, 62), sharex=False, sharey=False)
    src_frames = []
    for idx, (title, series) in enumerate(panels):
        src_frames.extend(_draw_wallet_distribution_panel(axes[idx], series, title, chr(ord("a") + idx)))
    src = pd.concat(src_frames, ignore_index=True) if src_frames else pd.DataFrame()
    finalize_v15(fig, "4-2-3_微观_损益分布_决策轮数", src)


def fig_micro_wallet_pnl_baseline_distribution() -> None:
    runs = latest_runs_of("rq1_panel")[:10]
    if not runs:
        return
    fig, axes = plt.subplots(5, 2, figsize=fig_size(COL_DOUBLE_MM, 182), sharex=False, sharey=False)
    axes_flat = axes.flatten()
    src_frames = []
    for idx, run in enumerate(runs):
        cfg = config_name(run)
        title = market_title_for(cfg)
        dist = _run_dist(run, "baseline", "正常实验")
        src_frames.extend(_draw_wallet_distribution_panel(axes_flat[idx], [(dist, "正常实验", BLUE)], title, chr(ord("a") + idx)))
    for ax in axes_flat[len(runs):]:
        ax.set_axis_off()
    src = pd.concat(src_frames, ignore_index=True) if src_frames else pd.DataFrame()
    finalize_v15(fig, "4-2-1_微观_损益分布_正常实验", src)


def _find_run_path_by_suffix(suite: str, suffix: str) -> Path | None:
    for run in latest_runs_of(suite):
        cfg = config_name(run)
        if cfg.endswith(f"_{suffix}_s0") or cfg.endswith(f"_{suffix}"):
            return run
    return None


def fig_micro_wallet_pnl_ablation_distribution() -> None:
    fig, axes = plt.subplots(
        len(ABLATION_MODULES), len(BASE_MARKETS),
        figsize=fig_size(COL_DOUBLE_MM, 150),
        sharex=False,
        sharey=False,
    )
    if len(ABLATION_MODULES) == 1:
        axes = np.array([axes])
    colors = [BLUE, GREEN, GOLD, RED]
    src_frames = []
    for row_idx, module in enumerate(ABLATION_MODULES):
        conditions = [(module["baseline_suffix"], module["baseline_label"])] + list(module["ablation_suffixes"])
        for col_idx, mkt in enumerate(BASE_MARKETS):
            ax = axes[row_idx, col_idx]
            series = []
            suite = f"{module['key']}_{mkt}"
            for cond_idx, (suffix, label) in enumerate(conditions):
                run = _find_run_path_by_suffix(suite, suffix)
                if run is None:
                    continue
                series_label = label
                dist = _run_dist(run, f"ablation_{module['key']}", series_label)
                series.append((dist, series_label, colors[cond_idx % len(colors)]))
            title = f"{module['label']}·{MARKET_LABEL[mkt]}"
            panel = chr(ord("a") + row_idx * len(BASE_MARKETS) + col_idx)
            src_frames.extend(_draw_wallet_distribution_panel(ax, series, title, panel))
    src = pd.concat(src_frames, ignore_index=True) if src_frames else pd.DataFrame()
    finalize_v15(fig, "4-2-4_微观_损益分布_消融实验", src)


# === 4.2.4 micro ablation behavior ===========================================
def _find_run_by_suffix(suite: str, suffix: str):
    for run in latest_runs_of(suite):
        if config_name(run).endswith(f"_{suffix}_s0") or config_name(run).endswith(f"_{suffix}"):
            return metrics(run)
    return None


_ABL_COLORS = [GREEN, GOLD, VIOLET]


def fig_micro_ablation_behavior() -> None:
    """4-2-4: per-module subplots showing how each ablation reshapes the micro
    behavior (累积主动交易成交率) compared to its baseline. No real-market line
    because the real Polymarket trade tape has no comparable per-tick
    execution-rate sequence — so each subplot shows baseline + ablation
    variants only.
    """
    n_modules = len(ABLATION_MODULES)
    n_markets = len(BASE_MARKETS)
    fig, axes = plt.subplots(
        n_modules, n_markets,
        figsize=fig_size(COL_DOUBLE_MM, 56 * n_modules),
        sharey=False,
    )
    if n_modules == 1:
        axes = np.array([axes])
    src = []
    behavior_rows: list[dict] = []

    for row_idx, module in enumerate(ABLATION_MODULES):
        suite_prefix = module["key"]
        baseline_suffix = module["baseline_suffix"]
        ablations = module["ablation_suffixes"]
        for col_idx, mkt in enumerate(BASE_MARKETS):
            ax = axes[row_idx, col_idx]
            suite = f"{suite_prefix}_{mkt}"
            baseline = _find_run_by_suffix(suite, baseline_suffix)
            if baseline is None:
                ax.set_axis_off()
                continue

            baseline_path = micro_trade_count_behavior_path(
                baseline, f"正常·{module['baseline_label']}",
            )
            if not baseline_path.empty:
                baseline_path = baseline_path.copy()
                baseline_path["module"] = module["key"]
                src.extend(baseline_path.to_dict("records"))
                ax.plot(
                    baseline_path["cum_trades"], baseline_path["execution_rate"],
                    "o-", color=BLUE, lw=1.4, label=f"正常模拟·{module['baseline_label']}",
                )
                behavior_rows.append({
                    "module": module["key"],
                    "market": mkt,
                    "variant": "baseline",
                    "config": baseline["config"],
                    "final_execution_rate": float(baseline_path["execution_rate"].iloc[-1]),
                    "final_cancel_per_trade": float(baseline_path["cancel_per_trade"].iloc[-1]),
                    "n_fills": int(baseline["n_fills"]),
                })

            for (suf, abl_label), color in zip(ablations, _ABL_COLORS):
                abl = _find_run_by_suffix(suite, suf)
                if abl is None:
                    continue
                abl_path = micro_trade_count_behavior_path(abl, f"消融·{abl_label}")
                if abl_path.empty:
                    continue
                abl_path = abl_path.copy()
                abl_path["module"] = module["key"]
                src.extend(abl_path.to_dict("records"))
                ax.plot(
                    abl_path["cum_trades"], abl_path["execution_rate"],
                    "s--", color=color, lw=1.2, label=f"消融模拟·{abl_label}",
                )
                behavior_rows.append({
                    "module": module["key"],
                    "market": mkt,
                    "variant": "ablation",
                    "config": abl["config"],
                    "final_execution_rate": float(abl_path["execution_rate"].iloc[-1]),
                    "final_cancel_per_trade": float(abl_path["cancel_per_trade"].iloc[-1]),
                    "n_fills": int(abl["n_fills"]),
                })

            ax.set_title(f"{module['label']}·{MARKET_LABEL[mkt]}", fontsize=7.0)
            ax.set_xlabel("累积成交笔数")
            if col_idx == 0:
                ax.set_ylabel("累积主动交易成交率")
            ax.set_ylim(bottom=-0.02)
            ax.legend(loc="best", fontsize=5.6, ncol=2)
            integer_xaxis(ax)

        panel_label(axes[row_idx, 0], chr(ord("a") + row_idx))

    finalize_v15(fig, "4-2-4_微观_消融行为图", pd.DataFrame(src))
    pd.DataFrame(behavior_rows).round(4).to_csv(
        OUT_TBL / "表_4_2_4_微观消融行为汇总.csv", index=False,
    )


# === entry point ==============================================================
def run() -> None:
    print("4.2.1 baseline wallet PnL distribution ...")
    fig_micro_wallet_pnl_baseline_distribution()
    print("4.2.2 scale wallet PnL distribution ...")
    fig_micro_wallet_pnl_scale_distribution()
    print("4.2.3 tick wallet PnL distribution ...")
    fig_micro_wallet_pnl_tick_distribution()
    print("4.2.4 ablation wallet PnL distribution ...")
    fig_micro_wallet_pnl_ablation_distribution()


if __name__ == "__main__":
    run()
