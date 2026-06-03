"""v15 thesis 4.3 active-market validation figures + tables.

Covers:
  4.3.1 SpaceX 助推器回收市场的真实 vs 模拟价格路径

Run standalone or via ``scripts/thesis_v15_analysis.py``.
"""
from __future__ import annotations

import pandas as pd
import matplotlib.pyplot as plt

from _thesis_v15_common import (
    BLUE, GREEN, RED, NEUTRAL_MID, NEUTRAL_DARK,
    COL_DOUBLE_MM,
    OUT_TBL,
    market_title_for, safe_fig_name,
    latest_runs_of, metrics, integer_xaxis,
    simulated_trade_count_path, real_trade_count_path,
    real_actual_trade_count_path,
    split_terminal_settlement, draw_market_cutoff,
    trade_count_source_data,
    save_metric_table, finalize_v15,
    fig_size, fig_size_vstack, panel_label,
)


def fig_spacex_validation() -> None:
    rows = [metrics(r) for r in latest_runs_of("rq5_spacex")]
    if not rows:
        return
    r = rows[-1]
    fig, ax = plt.subplots(figsize=fig_size(COL_DOUBLE_MM, 72))
    ax.set_title(market_title_for(r["config"]), fontsize=7.5)
    sim = simulated_trade_count_path(r)
    if sim.empty:
        return
    real = real_trade_count_path(r, sim)
    ax.plot(sim["cum_trades"], sim["yes_mid"], color=BLUE, lw=1.7, label="模拟市场价格")
    if len(real):
        real.to_csv(OUT_TBL / "表_4_3_SpaceX真实市场YES价格路径.csv", index=False)
        real_plot, cutoff_x = split_terminal_settlement(real, r["truth"], "cum_trades")
        ax.plot(real_plot["cum_trades"], real_plot["yes_price"], color=NEUTRAL_DARK, lw=1.35, alpha=0.9, label="真实市场价格")
        step = max(len(real_plot) // 18, 1)
        ax.scatter(real_plot["cum_trades"].iloc[::step], real_plot["yes_price"].iloc[::step], s=8, color=NEUTRAL_DARK, alpha=0.75, linewidths=0)
        draw_market_cutoff(ax, cutoff_x)
    ax.axhline(r["truth"], color=RED if r["truth"] == 0 else GREEN, ls="--", lw=0.9, label="_nolegend_")
    ax.axhline(r["signal_mu"], color=NEUTRAL_MID, ls=":", lw=0.8, label="_nolegend_")
    ax.set_xlabel("累积成交笔数")
    ax.set_ylabel("YES 价格")
    ax.set_ylim(-0.03, 1.03)
    ax.legend(loc="best", fontsize=6.2)
    integer_xaxis(ax)
    finalize_v15(fig, f"4-3-1_{safe_fig_name(market_title_for(r['config']))}_价格图", trade_count_source_data(sim, real))

    real_actual = real_actual_trade_count_path(r)
    fig, axes = plt.subplots(2, 1, figsize=fig_size_vstack(2, panel_mm=50), sharey=True)
    source = []
    ax = axes[0]
    if not real_actual.empty:
        real_plot, cutoff_x = split_terminal_settlement(real_actual, r["truth"], "cum_trades")
        source.extend(trade_count_source_data(pd.DataFrame(), real_actual).to_dict("records"))
        ax.plot(real_plot["cum_trades"], real_plot["yes_price"], color=NEUTRAL_DARK, lw=1.25, label="真实市场价格")
        step = max(len(real_plot) // 18, 1)
        ax.scatter(real_plot["cum_trades"].iloc[::step], real_plot["yes_price"].iloc[::step], s=8, color=NEUTRAL_DARK, alpha=0.75, linewidths=0)
        draw_market_cutoff(ax, cutoff_x)
    ax.axhline(r["truth"], color=RED if r["truth"] == 0 else GREEN, ls="--", lw=0.9, label="_nolegend_")
    ax.axhline(r["signal_mu"], color=NEUTRAL_MID, ls=":", lw=0.8, label="_nolegend_")
    ax.set_title(market_title_for(r["config"]), fontsize=7.5)
    ax.set_xlabel("真实累积成交笔数")
    ax.set_ylabel("YES 价格")
    ax.set_ylim(-0.03, 1.03)
    ax.legend(loc="best", fontsize=6.2)
    integer_xaxis(ax)
    panel_label(ax, "a")

    ax = axes[1]
    source.extend(trade_count_source_data(sim, pd.DataFrame()).to_dict("records"))
    ax.plot(sim["cum_trades"], sim["yes_mid"], color=BLUE, lw=1.5, label="模拟市场价格")
    ax.axhline(r["truth"], color=RED if r["truth"] == 0 else GREEN, ls="--", lw=0.9, label="_nolegend_")
    ax.axhline(r["signal_mu"], color=NEUTRAL_MID, ls=":", lw=0.8, label="_nolegend_")
    ax.set_xlabel("模拟累积成交笔数")
    ax.set_ylabel("YES 价格")
    ax.set_ylim(-0.03, 1.03)
    ax.legend(loc="best", fontsize=6.2)
    integer_xaxis(ax)
    panel_label(ax, "b")
    finalize_v15(fig, f"4-3-1_{safe_fig_name(market_title_for(r['config']))}_真实模拟分轴价格图", pd.DataFrame(source))
    save_metric_table(rows, "表_4_3_活跃市场验证_SpaceX指标.csv")


def run() -> None:
    print("4.3 SpaceX validation ...")
    fig_spacex_validation()


if __name__ == "__main__":
    run()
