"""v15 thesis analysis — orchestrator.

The actual figure/table generation lives in three sibling scripts:
  - scripts/thesis_v15_4_1_macro.py
  - scripts/thesis_v15_4_2_micro.py
  - scripts/thesis_v15_4_3_validation.py
plus the shared helper module scripts/_thesis_v15_common.py.

This file only wires them together so a single command runs everything:

    uv run python scripts/thesis_v15_analysis.py
"""
from __future__ import annotations

import argparse

import thesis_v15_4_1_macro as macro
import thesis_v15_4_2_micro as micro
import thesis_v15_4_2_patterns as patterns
import thesis_v15_4_3_validation as validation

from _thesis_v15_common import (
    BASE_MARKETS, MARKET_LABEL,
    OUT_ANALYSIS, OUT_FIG, OUT_TBL,
    latest_runs_of, market_title_for, metrics, result_label,
)


def write_experiment_analysis_markdown() -> None:
    lines = [
        "# v15 实验图表分析结论",
        "",
        "本文图表尽量只保留坐标、市场名称、图例和必要参考线；方向解释、好坏判断和跨图结论集中写在本文件中。",
        "",
        "## 4.1.1 宏观价格方向",
        "",
    ]
    rq1_rows = [metrics(r) for r in latest_runs_of("rq1_panel")]
    if rq1_rows:
        good = [r for r in rq1_rows if r["direction_score"] > 0]
        bad = [r for r in rq1_rows if r["direction_score"] <= 0]
        lines.append(f"- 十个验证市场中，方向得分为正的市场有 {len(good)} 个，方向得分非正的市场有 {len(bad)} 个。")
        lines.append("- 判断标准是模拟市场最终价格相对初始价格是否向真实结局方向移动。YES 结局市场中，价格越靠近 1.00 越接近真实结局；NO 结局市场中，YES 价格越靠近 0.00 越接近真实结局。")
        lines.append("- 成交次数映射图用于比较真实市场与模拟市场在相似交易活跃阶段的价格位置；真实模拟分轴图用于保留各自真实成交笔数，不强行把两个市场压到同一横轴尺度。")
        lines.append("")
        lines.append("| 市场 | 结局 | 初始价格 | 最终价格 | 方向得分 | 判断 |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for r in rq1_rows:
            lines.append(
                f"| {market_title_for(r['config'])} | {r['truth_label']} | "
                f"{r['start_mid']:.3f} | {r['end_mid']:.3f} | {r['direction_score']:.3f} | {result_label(r)} |"
            )
        lines.append("")

    lines.extend([
        "## 4.1.2 智能体数量扩展",
        "",
        "- 价格图将不同智能体数量作为多条模拟曲线，并补充真实市场价格路径。映射版用于观察相似成交活跃阶段下的方向关系，真实模拟分轴版用于避免真实市场成交笔数远大于模拟成交笔数时造成横轴压缩。",
        "- 成交图按市场拆成两个子图，并使用每智能体每 tick 成交、每智能体成交额等标准化指标。这样分析的是规模扩展后的个体平均流动性，而不是智能体数量增加必然带来的总成交笔数上升。",
        "",
    ])
    scale_rows = []
    for mkt in BASE_MARKETS:
        for run in latest_runs_of(f"c1_{mkt}"):
            scale_rows.append(metrics(run))
    if scale_rows:
        lines.append("| 市场 | 智能体数量 | 最终价格 | 成交笔数 | 每智能体每tick成交 | 人均成交额 |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for r in sorted(scale_rows, key=lambda x: (x["market_key"], x["n_agents"])):
            lines.append(
                f"| {MARKET_LABEL.get(r['market_key'], r['market_key'])} | {r['n_agents']} | "
                f"{r['end_mid']:.3f} | {r['n_fills']} | {r['fills_per_agent_tick']:.4f} | {r['notional_per_agent']:.2f} |"
            )
        lines.append("")

    lines.extend([
        "## 4.1.3 决策轮数扩展",
        "",
        "- 决策轮数扩展图同样以累积成交笔数为横轴。这样可以观察长轮次是否带来新的价格发现，还是主要表现为交易过程被拉长。",
        "",
    ])
    tick_rows = []
    for mkt in BASE_MARKETS:
        for run in latest_runs_of(f"c3_{mkt}"):
            tick_rows.append(metrics(run))
    if tick_rows:
        lines.append("| 市场 | 决策轮数 | 最终价格 | 成交笔数 | 波动率 | 最大单步变化 |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for r in sorted(tick_rows, key=lambda x: (x["market_key"], x["n_ticks"])):
            lines.append(
                f"| {MARKET_LABEL.get(r['market_key'], r['market_key'])} | {r['n_ticks']} | "
                f"{r['end_mid']:.3f} | {r['n_fills']} | {r['volatility']:.4f} | {r['max_abs_step']:.4f} |"
            )
        lines.append("")

    lines.extend([
        "## 4.1.4 宏观模块消融价格",
        "",
        "- 每个子图按消融模块（画像分布 c4 / 思考模式 c5 / 信念更新工具 c6）和市场展开，同时画出真实市场、正常模拟、消融模拟三条价格路径，横轴是累积成交笔数。",
        "- 判断重点是消融后的模拟曲线是否相对正常模拟显著偏离真实市场价格路径；偏离方向给出该模块对宏观价格收敛性的方向性贡献。",
        "",
        "## 4.2 微观交易者行为",
        "",
        "- 微观章节只保留三类图表：画像数量分布、损益分布、信念价格差距。每一类图都分别覆盖正常实验、智能体规模扩展、决策轮数扩展和模块消融实验，保证图表结构与研究问题一一对应。",
        "- 画像数量分布图用于观察不同实验条件下四类交易者画像的数量占比变化。聚类优化后移除了容易受运行环境影响的 API 推理耗时特征，并重新拟合为更稳定的 4 类画像：激进套利型、信念锚定型、频繁挂撤型、信号反向型。",
        "- 损益分布图以最终损益为横轴、钱包密度为纵轴，只保留平滑分布曲线，不再叠加柱状图。若分布右尾拉长或右侧局部峰值明显，说明少数钱包获得了更高损益，可用于讨论“马太效应”式的微观收益分化。",
        "- 信念价格差距图以累积成交笔数为横轴，同时呈现群体平均信念、信念四分位区间和模拟市场价格，用于判断智能体认知是否随交易推进靠近市场价格。",
        "",
        "## 4.3 活跃市场验证",
        "",
    ])
    spacex_rows = [metrics(r) for r in latest_runs_of("rq5_spacex")]
    if spacex_rows:
        r = spacex_rows[-1]
        lines.append(f"- 活跃市场验证市场为 {market_title_for(r['config'])}。该市场最终结局为 {r['truth_label']}。")
        lines.append(f"- 模拟市场从 {r['start_mid']:.3f} 变化到 {r['end_mid']:.3f}，方向得分为 {r['direction_score']:.3f}。真实市场价格路径用于事后验证活跃期模拟判断与最终关闭结果之间的关系。")
        lines.append("- 映射版价格图用于比较相似成交进度，真实模拟分轴版用于保留真实市场和模拟市场各自的成交笔数尺度。")
        lines.append("")

    (OUT_ANALYSIS / "v15_experiment_analysis.md").write_text("\n".join(lines))


def main(refit_patterns: bool = False, patterns_only: bool = False) -> None:
    if not patterns_only:
        macro.run()
        micro.run()
        validation.run()
    patterns.run(refit=refit_patterns)
    if not patterns_only:
        print("analysis markdown ...")
        write_experiment_analysis_markdown()
    print(f"figures -> {OUT_FIG} (split by format under pdf/png/svg/tiff)")
    print(f"tables  -> {OUT_TBL}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refit-patterns", action="store_true", help="强制重新拟合行为模式模型")
    parser.add_argument("--patterns-only", action="store_true", help="只跑 §4.2 行为模式分析，跳过宏观/验证/微观旧图")
    args = parser.parse_args()
    main(refit_patterns=args.refit_patterns, patterns_only=args.patterns_only)
