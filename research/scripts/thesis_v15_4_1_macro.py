"""v15 thesis 4.1 macro-level figures + tables.

Covers:
  4.1.1 跨市场宏观价格 (rq1 panel)
  4.1.2 智能体数量扩展 (c1)
  4.1.3 决策轮数扩展 (c3)
  4.1.4 宏观模块消融价格 (c4/c5/c6) — real / baseline / ablation lines per module

Run standalone or via ``scripts/thesis_v15_analysis.py``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _thesis_v15_common import (
    BLUE, GREEN, RED, GOLD, TEAL, VIOLET,
    NEUTRAL_MID, NEUTRAL_DARK,
    BASE_MARKETS, MARKET_LABEL, MARKET_COLOR,
    ACTION_ORDER, ABLATION_MODULES,
    COL_DOUBLE_MM,
    OUT_TBL,
    config_name, market_title_for, safe_fig_name,
    latest_runs_of, grouped,
    metrics, integer_xaxis, result_color, result_label,
    path_rows, real_path_for_plot, real_path_source_rows,
    split_terminal_settlement, draw_market_cutoff,
    simulated_trade_count_path, real_trade_count_path,
    real_actual_trade_count_path, try_real_trade_path,
    trade_count_source_data,
    save_metric_table, finalize_v15,
    fig_size, fig_size_vstack, panel_label,
)


# === 4.1.1 cross-market macro =================================================
def fig_macro_cross_market() -> list[dict]:
    rows = [metrics(r) for r in latest_runs_of("rq1_panel")]
    if not rows:
        return rows
    src = []

    fig, axes = plt.subplots(5, 2, figsize=fig_size(COL_DOUBLE_MM, 190), sharex=True, sharey=True)
    for ax, r in zip(axes.ravel(), rows):
        data = path_rows(r, r["config"])
        if not data:
            continue
        src.extend(data)
        df = pd.DataFrame(data)
        ax.plot(df["tick"], df["yes_mid"], color=BLUE, lw=1.05, marker="o", markersize=2.1, label="模拟市场价格")
        real = real_path_for_plot(r, df)
        if not real.empty:
            src.extend(real_path_source_rows(real))
            real_plot, cutoff_x = split_terminal_settlement(real, r["truth"], "mapped_tick")
            ax.plot(real_plot["mapped_tick"], real_plot["yes_price"], color=NEUTRAL_DARK, lw=0.9, alpha=0.78, label="真实市场价格")
            draw_market_cutoff(ax, cutoff_x)
        ax.axhline(r["truth"], color=result_color(r), ls="--", lw=0.8, label="_nolegend_")
        ax.axhline(0.5, color=NEUTRAL_MID, ls=":", lw=0.65)
        ax.set_title(market_title_for(r["config"]), fontsize=6.4)
        ax.set_ylim(-0.03, 1.03)
        integer_xaxis(ax)
    for ax in axes[-1, :]:
        ax.set_xlabel("决策轮次 tick")
    for ax in axes[:, 0]:
        ax.set_ylabel("YES 中间价")
    handles, labels = axes.ravel()[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=6.2, bbox_to_anchor=(0.5, 1.025))
    finalize_v15(fig, "4-1-1_宏观_跨市场价格图_tick", pd.DataFrame(src), pad=0.7)

    fig, ax = plt.subplots(figsize=fig_size(COL_DOUBLE_MM, 62))
    ordered = sorted(rows, key=lambda x: (x["truth"], x["direction_score"]))
    y = np.arange(len(ordered))
    vals = [r["direction_score"] for r in ordered]
    colors = [GREEN if v > 0 else RED for v in vals]
    labels = [r["config"].replace("rq1_", "").replace("_s0", "") for r in ordered]
    bars = ax.barh(y, vals, color=colors, edgecolor=NEUTRAL_DARK, linewidth=0.4)
    for bar, val in zip(bars, vals):
        bar.set_hatch("///" if val > 0 else "\\\\\\")
        x = val + (0.006 if val >= 0 else -0.006)
        ha = "left" if val >= 0 else "right"
        ax.text(x, bar.get_y() + bar.get_height() / 2, f"{val:+.3f}", va="center", ha=ha, fontsize=6.0)
    ax.axvline(0, color=NEUTRAL_DARK, lw=0.8)
    ax.set_xlim(min(vals) - 0.05, max(vals) + 0.05)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=6.2)
    ax.set_xlabel("朝真实结局移动幅度，正值更好")
    ax.set_title("跨市场方向得分", fontsize=7.5)
    finalize_v15(
        fig,
        "4-1-1_宏观_方向得分图",
        pd.DataFrame([{k: v for k, v in r.items() if k not in ("run", "mids", "action_mix")} for r in rows]),
    )

    save_metric_table(rows, "表_4_1_1_跨市场宏观指标.csv")
    fig_macro_cross_market_by_trade_count(rows)
    fig_macro_single_markets(rows)
    fig_macro_single_markets_by_trade_count(rows)
    fig_macro_single_markets_unmapped_trade_count(rows)
    return rows


def fig_macro_cross_market_by_trade_count(rows: list[dict]) -> None:
    fig, axes = plt.subplots(5, 2, figsize=fig_size(COL_DOUBLE_MM, 190), sharex=False, sharey=True)
    src = []
    for ax, r in zip(axes.ravel(), rows):
        sim = simulated_trade_count_path(r)
        if sim.empty:
            continue
        real = real_trade_count_path(r, sim)
        src.extend(trade_count_source_data(sim, real).to_dict("records"))
        ax.plot(sim["cum_trades"], sim["yes_mid"], color=BLUE, lw=1.05, marker="o", markersize=2.1, label="模拟市场价格")
        if not real.empty:
            real_plot, cutoff_x = split_terminal_settlement(real, r["truth"], "cum_trades")
            ax.plot(real_plot["cum_trades"], real_plot["yes_price"], color=NEUTRAL_DARK, lw=0.9, alpha=0.78, label="真实市场价格")
            draw_market_cutoff(ax, cutoff_x)
        ax.axhline(r["truth"], color=result_color(r), ls="--", lw=0.8, label="_nolegend_")
        ax.axhline(0.5, color=NEUTRAL_MID, ls=":", lw=0.65, label="_nolegend_")
        ax.set_title(market_title_for(r["config"]), fontsize=6.4)
        ax.set_ylim(-0.03, 1.03)
        integer_xaxis(ax)
    for ax in axes[-1, :]:
        ax.set_xlabel("累积成交笔数")
    for ax in axes[:, 0]:
        ax.set_ylabel("YES 价格")
    handles, labels = axes.ravel()[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=6.2, bbox_to_anchor=(0.5, 1.025))
    finalize_v15(fig, "4-1-1_宏观_跨市场价格图", pd.DataFrame(src), pad=0.7)


def fig_macro_single_markets(rows: list[dict]) -> None:
    for r in rows:
        data = path_rows(r, r["config"])
        if not data:
            continue
        df = pd.DataFrame(data)
        fig, ax = plt.subplots(figsize=fig_size(COL_DOUBLE_MM, 54))
        color = result_color(r)
        ax.plot(df["tick"], df["yes_mid"], color=BLUE, lw=1.5, marker="o", markersize=2.8, label="模拟市场价格")
        real = real_path_for_plot(r, df)
        source = df.to_dict("records")
        if not real.empty:
            real.to_csv(OUT_TBL / f"表_4_1_1_真实市场YES价格路径_{r['config']}.csv", index=False)
            source.extend(real_path_source_rows(real))
            real_plot, cutoff_x = split_terminal_settlement(real, r["truth"], "mapped_tick")
            ax.plot(real_plot["mapped_tick"], real_plot["yes_price"], color=NEUTRAL_DARK, lw=1.25, alpha=0.86, label="真实市场价格")
            step = max(len(real_plot) // 18, 1)
            ax.scatter(real_plot["mapped_tick"].iloc[::step], real_plot["yes_price"].iloc[::step], s=8, color=NEUTRAL_DARK, alpha=0.75, linewidths=0)
            draw_market_cutoff(ax, cutoff_x)
        else:
            ax.text(0.98, 0.08, "本地无真实成交数据", transform=ax.transAxes, ha="right", va="bottom", fontsize=6.2, color=NEUTRAL_DARK)
        ax.axhline(r["truth"], color=color, ls="--", lw=0.9, label="_nolegend_")
        ax.axhline(0.5, color=NEUTRAL_MID, ls=":", lw=0.8, label="_nolegend_")
        ax.set_title(market_title_for(r["config"]), fontsize=7.5)
        ax.set_xlabel("决策轮次 tick")
        ax.set_ylabel("YES 中间价")
        ax.set_ylim(-0.03, 1.03)
        integer_xaxis(ax)
        ax.legend(loc="best", fontsize=6.2)
        finalize_v15(fig, f"4-1-1_{safe_fig_name(market_title_for(r['config']))}_价格图_tick", pd.DataFrame(source))


def fig_macro_single_markets_by_trade_count(rows: list[dict]) -> None:
    for r in rows:
        sim = simulated_trade_count_path(r)
        if sim.empty:
            continue
        real = real_trade_count_path(r, sim)
        source = trade_count_source_data(sim, real)
        source.to_csv(OUT_TBL / f"表_4_1_1_成交次数映射价格路径_{r['config']}.csv", index=False)

        fig, ax = plt.subplots(figsize=fig_size(COL_DOUBLE_MM, 54))
        ax.plot(sim["cum_trades"], sim["yes_mid"], color=BLUE, lw=1.5, marker="o", markersize=2.8, label="模拟市场价格")
        if not real.empty:
            real_plot, cutoff_x = split_terminal_settlement(real, r["truth"], "cum_trades")
            ax.plot(real_plot["cum_trades"], real_plot["yes_price"], color=NEUTRAL_DARK, lw=1.25, alpha=0.86, label="真实市场价格")
            step = max(len(real_plot) // 18, 1)
            ax.scatter(real_plot["cum_trades"].iloc[::step], real_plot["yes_price"].iloc[::step], s=8, color=NEUTRAL_DARK, alpha=0.75, linewidths=0)
            draw_market_cutoff(ax, cutoff_x)
        else:
            ax.text(0.98, 0.08, "本地无真实成交数据", transform=ax.transAxes, ha="right", va="bottom", fontsize=6.2, color=NEUTRAL_DARK)
        ax.axhline(r["truth"], color=result_color(r), ls="--", lw=0.9, label="_nolegend_")
        ax.axhline(0.5, color=NEUTRAL_MID, ls=":", lw=0.8, label="_nolegend_")
        ax.set_title(market_title_for(r["config"]), fontsize=7.5)
        ax.set_xlabel("累积成交笔数")
        ax.set_ylabel("YES 价格")
        ax.set_ylim(-0.03, 1.03)
        ax.set_xlim(left=-0.5)
        integer_xaxis(ax)
        ax.legend(loc="best", fontsize=6.2)
        finalize_v15(fig, f"4-1-1_{safe_fig_name(market_title_for(r['config']))}_价格图", source)


def fig_macro_single_markets_unmapped_trade_count(rows: list[dict]) -> None:
    for r in rows:
        sim = simulated_trade_count_path(r)
        if sim.empty:
            continue
        real = real_actual_trade_count_path(r)
        fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=48), sharey=True)
        source = []
        ax = axes[0]
        if not real.empty:
            real_plot, cutoff_x = split_terminal_settlement(real, r["truth"], "cum_trades")
            source.extend(trade_count_source_data(pd.DataFrame(), real).to_dict("records"))
            ax.plot(real_plot["cum_trades"], real_plot["yes_price"], color=NEUTRAL_DARK, lw=1.25, label="真实市场价格")
            step = max(len(real_plot) // 18, 1)
            ax.scatter(real_plot["cum_trades"].iloc[::step], real_plot["yes_price"].iloc[::step], s=8, color=NEUTRAL_DARK, alpha=0.75, linewidths=0)
            draw_market_cutoff(ax, cutoff_x)
        ax.axhline(r["truth"], color=result_color(r), ls="--", lw=0.9, label="_nolegend_")
        ax.axhline(0.5, color=NEUTRAL_MID, ls=":", lw=0.8, label="_nolegend_")
        ax.set_title(market_title_for(r["config"]), fontsize=7.5)
        ax.set_xlabel("真实累积成交笔数")
        ax.set_ylabel("YES 价格")
        ax.set_ylim(-0.03, 1.03)
        ax.legend(loc="best", fontsize=6.2)
        integer_xaxis(ax)
        panel_label(ax, "a")

        ax = axes[1]
        source.extend(trade_count_source_data(sim, pd.DataFrame()).to_dict("records"))
        ax.plot(sim["cum_trades"], sim["yes_mid"], color=BLUE, lw=1.5, marker="o", markersize=2.8, label="模拟市场价格")
        ax.axhline(r["truth"], color=result_color(r), ls="--", lw=0.9, label="_nolegend_")
        ax.axhline(0.5, color=NEUTRAL_MID, ls=":", lw=0.8, label="_nolegend_")
        ax.set_xlabel("模拟累积成交笔数")
        ax.set_ylabel("YES 价格")
        ax.set_ylim(-0.03, 1.03)
        ax.legend(loc="best", fontsize=6.2)
        integer_xaxis(ax)
        panel_label(ax, "b")
        finalize_v15(fig, f"4-1-1_{safe_fig_name(market_title_for(r['config']))}_真实模拟分轴价格图", pd.DataFrame(source))


# === 4.1.2 scale (c1) =========================================================
def fig_scale() -> None:
    ns = [10, 20, 50, 100]
    by_mkt = {m: grouped(f"c1_{m}", r"_n(\d+)_") for m in BASE_MARKETS}
    colors = [BLUE, GREEN, GOLD, RED]
    metric_rows = []

    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=60))
    price_src = []
    for ax, mkt in zip(axes, BASE_MARKETS):
        sample_for_real = None
        max_sim_trades = 1.0
        for n, color in zip(ns, [BLUE, GREEN, GOLD, RED]):
            rs = by_mkt.get(mkt, {}).get(str(n), [])
            if not rs:
                continue
            r = rs[-1]
            sample_for_real = sample_for_real or r
            df = simulated_trade_count_path(r)
            if df.empty:
                continue
            df = df.copy()
            df["series"] = f"n={n}"
            max_sim_trades = max(max_sim_trades, float(df["cum_trades"].max()))
            price_src.extend(df.to_dict("records"))
            ax.plot(df["cum_trades"], df["yes_mid"], color=color, lw=1.0, label=f"n={n}")
        if sample_for_real is not None:
            real = try_real_trade_path(sample_for_real["slug"])
            if not real.empty:
                real = real.copy()
                real["cum_trades"] = real["frac"] * max_sim_trades
                real["trade_progress"] = real["frac"]
                real["config"] = sample_for_real["config"]
                real["market_title"] = MARKET_LABEL[mkt]
                real["truth"] = sample_for_real["truth"]
                real_plot, cutoff_x = split_terminal_settlement(real, sample_for_real["truth"], "cum_trades")
                price_src.extend(trade_count_source_data(pd.DataFrame(), real).to_dict("records"))
                ax.plot(real_plot["cum_trades"], real_plot["yes_price"], color=NEUTRAL_DARK, lw=1.2, alpha=0.85, label="真实市场价格")
                draw_market_cutoff(ax, cutoff_x)
        sample = next((rs[-1] for rs in by_mkt.get(mkt, {}).values() if rs), None)
        if sample:
            ax.axhline(sample["truth"], color=NEUTRAL_DARK, ls="--", lw=0.8, label="_nolegend_")
        ax.set_title(MARKET_LABEL[mkt], fontsize=7.5)
        ax.set_xlabel("累积成交笔数")
        ax.set_ylabel("YES 价格")
        ax.set_ylim(-0.03, 1.03)
        ax.legend(loc="best", fontsize=6.2)
        integer_xaxis(ax)
    panel_label(axes[0], "a")
    panel_label(axes[1], "b")
    finalize_v15(fig, "4-1-2_宏观_规模扩展价格图", pd.DataFrame(price_src))

    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=54))
    for mkt in BASE_MARKETS:
        ax = axes[BASE_MARKETS.index(mkt)]
        rs_by_n = by_mkt.get(mkt, {})
        xs, fills_norm, notional_norm = [], [], []
        for n in ns:
            rs = rs_by_n.get(str(n), [])
            if not rs:
                continue
            r = rs[-1]
            metric_rows.append(r)
            xs.append(n)
            fills_norm.append(r["fills_per_agent_tick"])
            notional_norm.append(r["notional_per_agent"] / 1000.0)
        ax.plot(xs, fills_norm, "o-", color=BLUE, label="成交/智能体/tick")
        ax.plot(xs, notional_norm, "s--", color=GREEN, label="人均成交额 k")
        ax.set_title(MARKET_LABEL[mkt], fontsize=7.5)
        ax.set_xlabel("智能体数量")
        ax.set_ylabel("标准化成交指标")
        ax.legend(loc="best", fontsize=5.8, ncol=2)
        integer_xaxis(ax)
        panel_label(ax, "a" if mkt == BASE_MARKETS[0] else "b")
    finalize_v15(fig, "4-1-2_宏观_规模扩展成交图", pd.DataFrame(metric_rows))

    for mkt in BASE_MARKETS:
        fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=50), sharey=True)
        source = []
        sample = next((rs[-1] for rs in by_mkt.get(mkt, {}).values() if rs), None)
        if sample is None:
            continue
        real = real_actual_trade_count_path(sample)
        ax = axes[0]
        if not real.empty:
            real_plot, cutoff_x = split_terminal_settlement(real, sample["truth"], "cum_trades")
            source.extend(trade_count_source_data(pd.DataFrame(), real).to_dict("records"))
            ax.plot(real_plot["cum_trades"], real_plot["yes_price"], color=NEUTRAL_DARK, lw=1.25, label="真实市场价格")
            draw_market_cutoff(ax, cutoff_x)
        ax.axhline(sample["truth"], color=NEUTRAL_DARK, ls="--", lw=0.8, label="_nolegend_")
        ax.axhline(0.5, color=NEUTRAL_MID, ls=":", lw=0.8, label="_nolegend_")
        ax.set_title(MARKET_LABEL[mkt], fontsize=7.5)
        ax.set_xlabel("真实累积成交笔数")
        ax.set_ylabel("YES 价格")
        ax.set_ylim(-0.03, 1.03)
        ax.legend(loc="best", fontsize=6.2)
        integer_xaxis(ax)
        panel_label(ax, "a")

        ax = axes[1]
        for n, color in zip(ns, colors):
            rs = by_mkt.get(mkt, {}).get(str(n), [])
            if not rs:
                continue
            df = simulated_trade_count_path(rs[-1])
            if df.empty:
                continue
            df = df.copy()
            df["series"] = f"n={n}"
            source.extend(df.to_dict("records"))
            ax.plot(df["cum_trades"], df["yes_mid"], color=color, lw=1.0, label=f"n={n}")
        ax.axhline(sample["truth"], color=NEUTRAL_DARK, ls="--", lw=0.8, label="_nolegend_")
        ax.axhline(0.5, color=NEUTRAL_MID, ls=":", lw=0.8, label="_nolegend_")
        ax.set_xlabel("模拟累积成交笔数")
        ax.set_ylabel("YES 价格")
        ax.set_ylim(-0.03, 1.03)
        ax.legend(loc="best", fontsize=6.2)
        integer_xaxis(ax)
        panel_label(ax, "b")
        finalize_v15(fig, f"4-1-2_{safe_fig_name(MARKET_LABEL[mkt])}_真实模拟分轴价格图", pd.DataFrame(source))
    save_metric_table(metric_rows, "表_4_1_2_规模扩展宏微观指标.csv")


# === 4.1.3 tick horizon (c3) ==================================================
def fig_tick_horizon() -> None:
    ts = [10, 20, 50, 100]
    by_mkt = {m: grouped(f"c3_{m}", r"_t(\d+)_") for m in BASE_MARKETS}
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=62))
    src = []
    metric_rows = []
    for ax, mkt in zip(axes, BASE_MARKETS):
        sample_for_real = None
        max_sim_trades = 1.0
        for t, color in zip(ts, [BLUE, GREEN, GOLD, RED]):
            rs = by_mkt.get(mkt, {}).get(str(t), [])
            if not rs:
                continue
            r = rs[-1]
            sample_for_real = sample_for_real or r
            metric_rows.append(r)
            df = simulated_trade_count_path(r)
            if df.empty:
                continue
            df = df.copy()
            df["series"] = f"{t}轮"
            max_sim_trades = max(max_sim_trades, float(df["cum_trades"].max()))
            src.extend(df.to_dict("records"))
            ax.plot(df["cum_trades"], df["yes_mid"], color=color, lw=1.0, label=f"{t}轮")
        if sample_for_real is not None:
            real = try_real_trade_path(sample_for_real["slug"])
            if not real.empty:
                real = real.copy()
                real["cum_trades"] = real["frac"] * max_sim_trades
                real["trade_progress"] = real["frac"]
                real["config"] = sample_for_real["config"]
                real["market_title"] = MARKET_LABEL[mkt]
                real["truth"] = sample_for_real["truth"]
                real_plot, cutoff_x = split_terminal_settlement(
                    real, sample_for_real["truth"], "cum_trades",
                )
                src.extend(trade_count_source_data(pd.DataFrame(), real).to_dict("records"))
                ax.plot(
                    real_plot["cum_trades"], real_plot["yes_price"],
                    color=NEUTRAL_DARK, lw=1.2, alpha=0.85, label="真实市场价格",
                )
                draw_market_cutoff(ax, cutoff_x)
        sample = next((rs[-1] for rs in by_mkt.get(mkt, {}).values() if rs), None)
        if sample:
            ax.axhline(sample["truth"], color=NEUTRAL_DARK, ls="--", lw=0.8, label="_nolegend_")
        ax.set_title(MARKET_LABEL[mkt], fontsize=7.5)
        ax.set_xlabel("累积成交笔数")
        ax.set_ylabel("YES 中间价")
        ax.set_ylim(-0.03, 1.03)
        ax.legend(loc="best", fontsize=6.2)
        integer_xaxis(ax)
    panel_label(axes[0], "a")
    panel_label(axes[1], "b")
    finalize_v15(fig, "4-1-3_宏观_轮数扩展价格图", pd.DataFrame(src))
    save_metric_table(metric_rows, "表_4_1_3_轮数扩展宏微观指标.csv")


# === 4.1.4 macro ablation price ==============================================
# Palette per module: baseline distinguishable from ablation variants.
_ABL_COLORS = [GREEN, GOLD, VIOLET]  # ablation variants


def _find_run_by_suffix(suite: str, suffix: str):
    """Return latest run dict for a c4/c5/c6 suite + concrete config suffix."""
    for run in latest_runs_of(suite):
        if config_name(run).endswith(f"_{suffix}_s0") or config_name(run).endswith(f"_{suffix}"):
            return metrics(run)
    return None


def fig_macro_ablation_price() -> None:
    """4-1-4: per-module subplots, each showing real / baseline / ablation lines.

    Layout: 3 rows (one per ablation module: c4 / c5 / c6) × 2 cols (markets).
    Each subplot uses the by-trade-count price-figure style from 4-1-1.
    """
    n_modules = len(ABLATION_MODULES)
    n_markets = len(BASE_MARKETS)
    fig, axes = plt.subplots(
        n_modules, n_markets,
        figsize=fig_size(COL_DOUBLE_MM, 62 * n_modules),
        sharey=True,
    )
    if n_modules == 1:
        axes = np.array([axes])
    src = []
    metric_rows: list[dict] = []

    for row_idx, module in enumerate(ABLATION_MODULES):
        suite_prefix = module["key"]
        baseline_suffix = module["baseline_suffix"]
        ablations = module["ablation_suffixes"]
        for col_idx, mkt in enumerate(BASE_MARKETS):
            ax = axes[row_idx, col_idx]
            suite = f"{suite_prefix}_{mkt}"
            baseline = _find_run_by_suffix(suite, baseline_suffix)
            ablation_runs = [(_find_run_by_suffix(suite, suf), label) for suf, label in ablations]
            if baseline is None:
                ax.set_axis_off()
                continue

            baseline_sim = simulated_trade_count_path(baseline)
            max_sim_trades = float(max(baseline_sim["cum_trades"].max(), 1.0)) if not baseline_sim.empty else 1.0
            for abl, _ in ablation_runs:
                if abl is None:
                    continue
                abl_sim = simulated_trade_count_path(abl)
                if not abl_sim.empty:
                    max_sim_trades = max(max_sim_trades, float(abl_sim["cum_trades"].max()))

            # real path mapped onto the wider of baseline/ablation horizontal axes
            real = try_real_trade_path(baseline["slug"])
            if not real.empty:
                real = real.copy()
                real["cum_trades"] = real["frac"] * max_sim_trades
                real["trade_progress"] = real["frac"]
                real["config"] = baseline["config"]
                real["market_title"] = MARKET_LABEL[mkt]
                real["truth"] = baseline["truth"]
                real_plot, cutoff_x = split_terminal_settlement(real, baseline["truth"], "cum_trades")
                src.extend(trade_count_source_data(pd.DataFrame(), real).to_dict("records"))
                ax.plot(
                    real_plot["cum_trades"], real_plot["yes_price"],
                    color=NEUTRAL_DARK, lw=1.2, alpha=0.85, label="真实市场价格",
                )
                draw_market_cutoff(ax, cutoff_x)

            if not baseline_sim.empty:
                baseline_sim_tagged = baseline_sim.copy()
                baseline_sim_tagged["series"] = f"正常模拟·{module['baseline_label']}"
                baseline_sim_tagged["module"] = module["key"]
                src.extend(baseline_sim_tagged.to_dict("records"))
                ax.plot(
                    baseline_sim["cum_trades"], baseline_sim["yes_mid"],
                    color=BLUE, lw=1.4, marker="o", markersize=2.4,
                    label=f"正常模拟·{module['baseline_label']}",
                )
                metric_rows.append({**baseline, "module": module["key"], "variant": "baseline"})

            for (abl, abl_label), color in zip(ablation_runs, _ABL_COLORS):
                if abl is None:
                    continue
                abl_sim = simulated_trade_count_path(abl)
                if abl_sim.empty:
                    continue
                tagged = abl_sim.copy()
                tagged["series"] = f"消融模拟·{abl_label}"
                tagged["module"] = module["key"]
                src.extend(tagged.to_dict("records"))
                ax.plot(
                    abl_sim["cum_trades"], abl_sim["yes_mid"],
                    color=color, lw=1.3, marker="s", markersize=2.2,
                    label=f"消融模拟·{abl_label}",
                )
                metric_rows.append({**abl, "module": module["key"], "variant": "ablation"})

            ax.axhline(baseline["truth"], color=NEUTRAL_DARK, ls="--", lw=0.8, label="_nolegend_")
            ax.axhline(0.5, color=NEUTRAL_MID, ls=":", lw=0.6, label="_nolegend_")
            ax.set_title(f"{module['label']}·{MARKET_LABEL[mkt]}", fontsize=7.0)
            ax.set_xlabel("累积成交笔数")
            if col_idx == 0:
                ax.set_ylabel("YES 价格")
            ax.set_ylim(-0.03, 1.03)
            ax.legend(loc="best", fontsize=5.6, ncol=2)
            integer_xaxis(ax)

        panel_label(axes[row_idx, 0], chr(ord("a") + row_idx))

    finalize_v15(fig, "4-1-4_宏观_消融价格图", pd.DataFrame(src))
    # Drop unserializable / heavy columns before saving the metric table.
    save_metric_table(metric_rows, "表_4_1_4_宏观消融指标.csv")


# === entry point ==============================================================
def run() -> None:
    print("4.1.1 cross-market macro ...")
    fig_macro_cross_market()
    print("4.1.2 scale ...")
    fig_scale()
    print("4.1.3 tick horizon ...")
    fig_tick_horizon()
    print("4.1.4 macro ablation price ...")
    fig_macro_ablation_price()


if __name__ == "__main__":
    run()
