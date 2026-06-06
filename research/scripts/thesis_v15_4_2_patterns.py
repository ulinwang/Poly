"""v15 论文 §4.2 行为模式分析。

对每个 v15 run 提取 per-agent 行为特征（动作组合 / 仓位轨迹 / 风险配置 /
反应度 / 结果 / reasoning 语义嵌入），在 rq1_panel 基线上做无监督 K-means
聚类提炼出 3–6 个可解释的行为模式，再把同一套模式应用到 c1/c3 规模实验和
c4/c5/c6 消融实验，输出：

- 每个 run 下 ``analysis/agent_features.parquet`` + ``agent_patterns.parquet``
- ``output/v15/_models/pattern_model_v1.joblib`` 等模型文件
- ``docs/v15/tables/表_4_2_行为模式_分布_全部.csv``
  ``docs/v15/tables/表_4_2_行为模式_特征指纹.csv``
- ``docs/v15/analysis/v15_behavioral_patterns.md`` 模式目录
- 五张图：``4_2_微观_行为模式_{规模分布_ethereum, 规模分布_robotaxi,
  消融分布, 特征指纹, 收益矩阵, 市场间持续性}``

reasoning 语义特征使用 ``TfidfVectorizer(1-2gram) + TruncatedSVD`` 投影到
6 维（不依赖外部模型，可完全离线复现）。
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA, TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from _thesis_v15_common import (
    ABLATION_MODULES,
    BASE_MARKETS,
    BLUE,
    COL_DOUBLE_MM,
    COL_SINGLE_MM,
    FIG_FORMATS,
    GOLD,
    GREEN,
    MARKET_LABEL,
    cumulative_trade_map,
    NEUTRAL_DARK,
    NEUTRAL_LIGHT,
    NEUTRAL_MID,
    OUT_ANALYSIS,
    OUT_FIG,
    OUT_TBL,
    RED,
    RQ1_MARKET_TITLE,
    TEAL,
    TRADING_ACTIONS,
    V15,
    VIOLET,
    config_name,
    fig_size,
    finalize_v15,
    latest_runs_of,
    load_actions,
    load_fills,
    load_positions,
    market_title_for,
    metrics as run_metrics,
    panel_label,
)


# === 常量与版本号 ============================================================
V_PATTERN = "v1"
ACTION_TRADING_TYPES = ["LIMIT", "MARKET", "CANCEL", "HOLD"]
SPLIT_MERGE_TYPES = ["SPLIT", "MERGE"]
BELIEF_ACTION = "UPDATE_BELIEF"
MARKET_MAKER_AGENT_ID = 999999

MODEL_DIR = V15 / "_models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Suite -> 类别. 用于在汇总图里把样本归到对应分面。
SCALE_SUITES = {
    "c1_ethereum": "n",
    "c1_robotaxi": "n",
    "c3_ethereum": "t",
    "c3_robotaxi": "t",
}
ABLATION_SUITES = {
    "c4_ethereum",
    "c4_robotaxi",
    "c5_ethereum",
    "c5_robotaxi",
    "c6_ethereum",
    "c6_robotaxi",
}
RQ1_SUITE = "rq1_panel"

# 命名占位（事后人工微调可直接改这个 dict 或 patterns.md）
DEFAULT_PATTERN_NAME_POOL = [
    "信念锚定型",
    "频繁挂撤型",
    "激进套利型",
    "观望保守型",
    "动量跟随型",
    "信号反向型",
]

PATTERN_PALETTE = [BLUE, RED, GREEN, GOLD, VIOLET, TEAL]


# === 路径辅助 ===============================================================
def _features_path(run: Path) -> Path:
    return run / "analysis" / "agent_features.parquet"


def _emb_path(run: Path) -> Path:
    return run / "analysis" / "agent_reasoning_emb.parquet"


def _patterns_path(run: Path) -> Path:
    return run / "analysis" / "agent_patterns.parquet"


def _model_paths() -> dict[str, Path]:
    return {
        "kmeans": MODEL_DIR / f"pattern_model_{V_PATTERN}.joblib",
        "scaler": MODEL_DIR / f"pattern_scaler_{V_PATTERN}.joblib",
        "pca": MODEL_DIR / f"pattern_pca_{V_PATTERN}.joblib",
        "text_vec": MODEL_DIR / f"pattern_text_vec_{V_PATTERN}.joblib",
        "text_svd": MODEL_DIR / f"pattern_text_svd_{V_PATTERN}.joblib",
        "winsor": MODEL_DIR / f"pattern_winsor_{V_PATTERN}.joblib",
        "meta": MODEL_DIR / f"pattern_meta_{V_PATTERN}.json",
    }


# === 数据加载 ===============================================================
def all_v15_runs() -> list[Path]:
    suites = (
        [RQ1_SUITE]
        + [s for s in SCALE_SUITES]
        + [s for s in ABLATION_SUITES]
        + ["rq5_spacex"]
    )
    runs: list[Path] = []
    for suite in suites:
        runs.extend(latest_runs_of(suite))
    return runs


def _safe_read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    return df


def _suite_of(run: Path) -> str:
    return run.parent.name


# === 特征工程 ===============================================================
ACTION_FEATURES = [
    "share_LIMIT",
    "share_MARKET",
    "share_CANCEL",
    "share_HOLD",
    "share_SPLITMERGE",
    "action_entropy",
    "cancel_to_submit_ratio",
]
TRAJECTORY_FEATURES = [
    "net_position_acf1",
    "max_drawdown_norm",
    "mean_holding_period",
    "flip_count",
    "terminal_exposure_ratio",
]
RISK_FEATURES = [
    "mean_size_pct_capital",
    "max_size_pct_capital",
    "cash_deployment_slope",
    "size_cv",
]
REACTIVITY_FEATURES = [
    "belief_delta_mean_abs",
    "belief_vs_price_corr",
    "position_vs_midslope_match",
]
OUTCOME_FEATURES = [
    "final_pnl_norm",
    "trade_win_rate",
    "info_contribution_proxy",
]
STRUCTURAL_FEATURES = (
    ACTION_FEATURES
    + TRAJECTORY_FEATURES
    + RISK_FEATURES
    + REACTIVITY_FEATURES
    + OUTCOME_FEATURES
)
EMB_DIMS = 6
EMB_FEATURES = [f"emb_{i}" for i in range(EMB_DIMS)]
ALL_FEATURES = STRUCTURAL_FEATURES + EMB_FEATURES

FEATURE_LABEL_ZH = {
    "share_LIMIT": "限价单占比",
    "share_MARKET": "市价单占比",
    "share_CANCEL": "撤单占比",
    "share_HOLD": "观望占比",
    "share_SPLITMERGE": "拆分合并占比",
    "action_entropy": "动作熵",
    "cancel_to_submit_ratio": "撤单挂单比",
    "net_position_acf1": "净仓位自相关",
    "max_drawdown_norm": "最大回撤",
    "mean_holding_period": "平均持仓周期",
    "flip_count": "仓位翻转次数",
    "terminal_exposure_ratio": "终态敞口比",
    "mean_size_pct_capital": "下单规模均值占比",
    "max_size_pct_capital": "下单规模峰值占比",
    "cash_deployment_slope": "现金投入斜率",
    "size_cv": "下单规模变异系数",
    "belief_delta_mean_abs": "信念变动幅度",
    "belief_vs_price_corr": "信念-价格相关",
    "position_vs_midslope_match": "仓位顺势比例",
    "mean_api_latency_ms": "推理耗时",
    "final_pnl_norm": "归一收益",
    "trade_win_rate": "胜率",
    "info_contribution_proxy": "信息贡献",
}
for i in range(EMB_DIMS):
    FEATURE_LABEL_ZH[f"emb_{i}"] = f"语义维{i + 1}"


def _action_entropy(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    p = np.array([v / total for v in counts.values() if v > 0], dtype=float)
    return float(-(p * np.log(p + 1e-12)).sum() / math.log(max(len(p), 2)))


def _acf1(x: np.ndarray) -> float:
    if len(x) < 3:
        return 0.0
    x = x - x.mean()
    denom = (x ** 2).sum()
    if denom < 1e-12:
        return 0.0
    return float((x[1:] * x[:-1]).sum() / denom)


def _ols_slope(y: np.ndarray) -> float:
    n = len(y)
    if n < 3 or not np.isfinite(y).any():
        return 0.0
    x = np.arange(n, dtype=float)
    x_m = x - x.mean()
    y_m = y - np.nanmean(y)
    denom = (x_m ** 2).sum()
    if denom < 1e-12:
        return 0.0
    return float((x_m * y_m).sum() / denom)


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return 0.0
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 3:
        return 0.0
    sa, sb = np.std(a[mask]), np.std(b[mask])
    if sa < 1e-9 or sb < 1e-9:
        return 0.0
    return float(np.corrcoef(a[mask], b[mask])[0, 1])


@dataclass
class RunRawTables:
    actions: pd.DataFrame
    fills: pd.DataFrame
    positions: pd.DataFrame
    personas: pd.DataFrame
    mids: pd.Series


def _load_run_raw(run: Path) -> RunRawTables:
    actions = load_actions(run)
    fills = load_fills(run)
    positions = load_positions(run)
    personas = _safe_read(run / "raw" / "agent_personas.parquet")
    if actions.empty:
        mids = pd.Series(dtype=float)
    else:
        non_belief = actions[actions["action_type"] != BELIEF_ACTION]
        mids = (
            non_belief.dropna(subset=["yes_mid_after"])
            .groupby("tick_idx")["yes_mid_after"]
            .last()
            .astype(float)
        )
    return RunRawTables(actions=actions, fills=fills, positions=positions, personas=personas, mids=mids)


def _structural_features_for_run(run: Path, tables: RunRawTables) -> pd.DataFrame:
    actions = tables.actions
    positions = tables.positions
    fills = tables.fills
    personas = tables.personas
    mids = tables.mids

    if personas.empty:
        return pd.DataFrame(columns=["sim_id", "agent_id"] + STRUCTURAL_FEATURES)

    sim_id = str(personas["sim_id"].iloc[0])
    keep_cols = ["agent_id", "capital_initial"]
    if "persona_type" in personas.columns:
        keep_cols.append("persona_type")
    agents = personas[keep_cols].copy()
    agents["capital_initial"] = agents["capital_initial"].astype(float).clip(lower=1e-6)
    if "persona_type" not in agents.columns:
        agents["persona_type"] = ""

    rows: list[dict] = []
    by_agent_actions = (
        {aid: g for aid, g in actions.groupby("agent_id")} if not actions.empty else {}
    )
    by_agent_positions = (
        {aid: g for aid, g in positions.groupby("agent_id")} if not positions.empty else {}
    )
    by_agent_fills_taker = (
        {aid: g for aid, g in fills.groupby("taker_agent_id")} if not fills.empty else {}
    )
    by_agent_fills_maker = (
        {aid: g for aid, g in fills.groupby("maker_agent_id")} if not fills.empty else {}
    )

    mid_per_tick = mids.to_dict()
    sorted_ticks = sorted(mid_per_tick)
    mid_slope = {}
    for i, t in enumerate(sorted_ticks):
        prev = sorted_ticks[i - 1] if i > 0 else None
        mid_slope[t] = mid_per_tick[t] - mid_per_tick[prev] if prev is not None else 0.0

    for _, persona in agents.iterrows():
        aid = int(persona["agent_id"])
        cap = float(persona["capital_initial"])
        a = by_agent_actions.get(aid, pd.DataFrame())
        p = by_agent_positions.get(aid, pd.DataFrame())
        f_taker = by_agent_fills_taker.get(aid, pd.DataFrame())
        f_maker = by_agent_fills_maker.get(aid, pd.DataFrame())

        feat: dict[str, float] = {}

        # --- A. 动作组合 ---
        trade_rows = a[a["action_type"].isin(TRADING_ACTIONS)]
        counts = Counter(trade_rows["action_type"].tolist())
        total_trades = sum(counts.values())
        for k in ACTION_TRADING_TYPES:
            feat[f"share_{k}"] = counts.get(k, 0) / total_trades if total_trades else 0.0
        feat["share_SPLITMERGE"] = (
            sum(counts.get(k, 0) for k in SPLIT_MERGE_TYPES) / total_trades if total_trades else 0.0
        )
        feat["action_entropy"] = _action_entropy(counts) if counts else 0.0
        submits = counts.get("LIMIT", 0) + counts.get("MARKET", 0)
        feat["cancel_to_submit_ratio"] = min(counts.get("CANCEL", 0) / submits, 5.0) if submits else 0.0

        # --- B. 仓位轨迹 ---
        if not p.empty:
            p_sorted = p.sort_values("tick_idx")
            net = (p_sorted["yes_shares"].astype(float) - p_sorted["no_shares"].astype(float)).to_numpy()
            pnl = (
                p_sorted["realized_pnl"].astype(float) + p_sorted["unrealized_pnl"].astype(float)
            ).to_numpy()
            feat["net_position_acf1"] = _acf1(net)
            running_max = np.maximum.accumulate(pnl)
            drawdown = (pnl - running_max).min() if len(pnl) else 0.0
            feat["max_drawdown_norm"] = float(drawdown) / cap
            diffs = np.diff(np.sign(net))
            feat["flip_count"] = int((diffs != 0).sum())
            # holding period: 相邻非零段长度均值
            in_pos = net != 0
            run_lengths: list[int] = []
            cur = 0
            for v in in_pos:
                if v:
                    cur += 1
                elif cur > 0:
                    run_lengths.append(cur)
                    cur = 0
            if cur > 0:
                run_lengths.append(cur)
            feat["mean_holding_period"] = float(np.mean(run_lengths)) if run_lengths else 0.0
            last_mid = float(mids.iloc[-1]) if len(mids) else 0.5
            terminal_net = float(net[-1]) if len(net) else 0.0
            feat["terminal_exposure_ratio"] = abs(terminal_net) * last_mid / cap
        else:
            feat["net_position_acf1"] = 0.0
            feat["max_drawdown_norm"] = 0.0
            feat["mean_holding_period"] = 0.0
            feat["flip_count"] = 0
            feat["terminal_exposure_ratio"] = 0.0

        # --- C. 风险配置 ---
        submit_rows = a[a["action_type"].isin(["LIMIT", "MARKET"])]
        size_pcts = submit_rows["size_usd"].astype(float) / cap if not submit_rows.empty else pd.Series(dtype=float)
        feat["mean_size_pct_capital"] = float(size_pcts.mean()) if not size_pcts.empty else 0.0
        feat["max_size_pct_capital"] = float(size_pcts.max()) if not size_pcts.empty else 0.0
        if not p.empty:
            p_sorted = p.sort_values("tick_idx")
            deploy = 1.0 - p_sorted["cash"].astype(float) / cap
            feat["cash_deployment_slope"] = _ols_slope(deploy.to_numpy())
        else:
            feat["cash_deployment_slope"] = 0.0
        sizes = submit_rows["size_usd"].astype(float).to_numpy()
        if len(sizes) >= 2 and sizes.mean() > 1e-9:
            feat["size_cv"] = float(sizes.std() / sizes.mean())
        else:
            feat["size_cv"] = 0.0

        # --- D. 反应度 ---
        belief_rows = a[a["action_type"] == BELIEF_ACTION].sort_values("tick_idx")
        if not belief_rows.empty:
            beliefs = belief_rows["price"].astype(float).to_numpy()
            ticks = belief_rows["tick_idx"].astype(int).to_numpy()
            feat["belief_delta_mean_abs"] = float(np.abs(np.diff(beliefs)).mean()) if len(beliefs) > 1 else 0.0
            aligned_mid = np.array([mid_per_tick.get(t, np.nan) for t in ticks], dtype=float)
            feat["belief_vs_price_corr"] = _safe_corr(beliefs, aligned_mid)
        else:
            feat["belief_delta_mean_abs"] = 0.0
            feat["belief_vs_price_corr"] = 0.0

        if not p.empty and mid_slope:
            p_sorted = p.sort_values("tick_idx")
            net = (p_sorted["yes_shares"].astype(float) - p_sorted["no_shares"].astype(float)).to_numpy()
            ticks_p = p_sorted["tick_idx"].astype(int).to_numpy()
            dpos = np.diff(net)
            dmid = np.array([mid_slope.get(ticks_p[i + 1], 0.0) for i in range(len(dpos))], dtype=float)
            mask = (np.abs(dpos) > 1e-9) & (np.abs(dmid) > 1e-9)
            if mask.any():
                feat["position_vs_midslope_match"] = float(
                    (np.sign(dpos[mask]) == np.sign(dmid[mask])).mean()
                )
            else:
                feat["position_vs_midslope_match"] = 0.5
        else:
            feat["position_vs_midslope_match"] = 0.5

        latencies = a["api_latency_ms"].astype(float)
        latencies = latencies[latencies > 0]
        feat["mean_api_latency_ms"] = float(latencies.mean()) if not latencies.empty else 0.0

        # --- E. 结果 ---
        if not p.empty:
            last = p.sort_values("tick_idx").iloc[-1]
            final_pnl = float(last["realized_pnl"]) + float(last["unrealized_pnl"])
            feat["final_pnl_norm"] = final_pnl / cap
        else:
            feat["final_pnl_norm"] = 0.0

        # trade_win_rate: 每笔 fill 后续 mid 是否朝有利方向。
        wins = 0
        total = 0
        for src, side_col in ((f_taker, "maker_side"), (f_maker, "maker_side")):
            if src.empty:
                continue
            for _, fr in src.iterrows():
                t = int(fr["tick_idx"])
                # taker buys when maker_side == 'SELL'；price 是 yes 概率视角
                # 我们简化为：若 mid 在 fill 后向有利方向移动则记胜
                cur_mid = mid_per_tick.get(t)
                if cur_mid is None:
                    continue
                next_ticks = [tt for tt in sorted_ticks if tt > t]
                if not next_ticks:
                    continue
                next_mid = mid_per_tick.get(next_ticks[0])
                if next_mid is None:
                    continue
                is_taker = src is f_taker
                outcome_is_yes = str(fr["outcome"]).upper() == "YES"
                taker_buys = str(fr["maker_side"]).upper() == "SELL"
                # taker 买 YES，价格上涨为胜
                if is_taker:
                    bought_yes_side = outcome_is_yes and taker_buys
                    bought_no_side = (not outcome_is_yes) and taker_buys
                    if bought_yes_side and next_mid > cur_mid:
                        wins += 1
                    elif bought_no_side and next_mid < cur_mid:
                        wins += 1
                    elif (not taker_buys) and outcome_is_yes and next_mid < cur_mid:
                        wins += 1
                    elif (not taker_buys) and (not outcome_is_yes) and next_mid > cur_mid:
                        wins += 1
                else:
                    # maker：相反逻辑
                    maker_sells_yes = outcome_is_yes and taker_buys
                    if maker_sells_yes and next_mid < cur_mid:
                        wins += 1
                    elif outcome_is_yes and (not taker_buys) and next_mid > cur_mid:
                        wins += 1
                    elif (not outcome_is_yes) and taker_buys and next_mid > cur_mid:
                        wins += 1
                    elif (not outcome_is_yes) and (not taker_buys) and next_mid < cur_mid:
                        wins += 1
                total += 1
        feat["trade_win_rate"] = wins / total if total else 0.0

        # info_contribution_proxy: Σ notional · sign(Δmid) · sign(belief - mid_before) / Σ notional
        contrib_num = 0.0
        contrib_den = 0.0
        belief_by_tick: dict[int, float] = {}
        if not belief_rows.empty:
            for t, v in zip(
                belief_rows["tick_idx"].astype(int).to_numpy(),
                belief_rows["price"].astype(float).to_numpy(),
            ):
                belief_by_tick[int(t)] = float(v)
        if not f_taker.empty:
            for _, fr in f_taker.iterrows():
                t = int(fr["tick_idx"])
                notional = float(fr["notional"])
                cur_mid = mid_per_tick.get(t)
                next_ticks_local = [tt for tt in sorted_ticks if tt > t]
                if cur_mid is None or not next_ticks_local:
                    continue
                next_mid = mid_per_tick.get(next_ticks_local[0])
                if next_mid is None:
                    continue
                belief = belief_by_tick.get(t, cur_mid)
                contrib_num += notional * np.sign(next_mid - cur_mid) * np.sign(belief - cur_mid)
                contrib_den += notional
        feat["info_contribution_proxy"] = contrib_num / contrib_den if contrib_den > 1e-9 else 0.0

        feat["sim_id"] = sim_id
        feat["agent_id"] = aid
        feat["suite"] = _suite_of(run)
        feat["config"] = config_name(run)
        feat["capital_initial"] = cap
        pt = persona["persona_type"] if "persona_type" in persona.index else ""
        feat["persona_type"] = "" if pd.isna(pt) else str(pt)
        rows.append(feat)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[["sim_id", "agent_id", "suite", "config", "capital_initial", "persona_type"] + STRUCTURAL_FEATURES]
    return df


def _reasoning_corpus_for_run(run: Path, tables: RunRawTables) -> pd.DataFrame:
    """每 agent 一行：(sim_id, agent_id, reasoning_text)。"""
    actions = tables.actions
    if actions.empty:
        return pd.DataFrame(columns=["sim_id", "agent_id", "reasoning"])
    use = actions.copy()
    use["reasoning"] = use["reasoning"].fillna("").astype(str)
    use = use[use["reasoning"].str.len() > 0]
    if use.empty:
        return pd.DataFrame(columns=["sim_id", "agent_id", "reasoning"])
    sim_id = str(use["sim_id"].iloc[0])

    def _join(g: pd.DataFrame) -> str:
        text = " ".join(g["reasoning"].tolist())
        if len(text) > 8000:
            text = text[:4000] + " " + text[-4000:]
        return text

    grouped = use.groupby("agent_id", as_index=False).agg(reasoning=("reasoning", lambda g: _join(pd.DataFrame({"reasoning": g}))))
    grouped["sim_id"] = sim_id
    return grouped[["sim_id", "agent_id", "reasoning"]]


# --- 缓存逻辑 -----------
def _needs_recompute(target: Path, sources: Iterable[Path]) -> bool:
    if not target.exists():
        return True
    tgt_mtime = target.stat().st_mtime
    for s in sources:
        if s.exists() and s.stat().st_mtime > tgt_mtime:
            return True
    return False


def compute_or_load_features(runs: list[Path], force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """扫描所有 run，按需重算 per-agent 结构化特征 + reasoning 语料缓存。

    返回拼接后的 (structural_df, reasoning_df)。
    """
    struct_frames: list[pd.DataFrame] = []
    reasoning_frames: list[pd.DataFrame] = []

    for run in runs:
        raw_dir = run / "raw"
        sources = [
            raw_dir / "agent_actions.parquet",
            raw_dir / "agent_fills.parquet",
            raw_dir / "agent_positions.parquet",
            raw_dir / "agent_personas.parquet",
        ]
        feat_path = _features_path(run)
        reasoning_path = run / "analysis" / "agent_reasoning_text.parquet"
        feat_path.parent.mkdir(parents=True, exist_ok=True)

        need_struct = force or _needs_recompute(feat_path, sources)
        need_text = force or _needs_recompute(reasoning_path, [raw_dir / "agent_actions.parquet"])

        if need_struct or need_text:
            tables = _load_run_raw(run)
            if need_struct:
                df_struct = _structural_features_for_run(run, tables)
                if not df_struct.empty:
                    df_struct.to_parquet(feat_path, index=False)
            if need_text:
                df_text = _reasoning_corpus_for_run(run, tables)
                if not df_text.empty:
                    df_text.to_parquet(reasoning_path, index=False)

        if feat_path.exists():
            struct_frames.append(pd.read_parquet(feat_path))
        if reasoning_path.exists():
            reasoning_frames.append(pd.read_parquet(reasoning_path).assign(suite=_suite_of(run), config=config_name(run)))

    struct_all = pd.concat(struct_frames, ignore_index=True) if struct_frames else pd.DataFrame()
    reasoning_all = pd.concat(reasoning_frames, ignore_index=True) if reasoning_frames else pd.DataFrame()
    return struct_all, reasoning_all


# === 聚类拟合 ===============================================================
def _winsorize_fit(X: pd.DataFrame, lower: float = 0.01, upper: float = 0.99) -> dict[str, tuple[float, float]]:
    bounds = {}
    for c in X.columns:
        vals = X[c].astype(float)
        lo = float(np.nanquantile(vals, lower)) if vals.notna().any() else 0.0
        hi = float(np.nanquantile(vals, upper)) if vals.notna().any() else 1.0
        if hi - lo < 1e-9:
            hi = lo + 1e-6
        bounds[c] = (lo, hi)
    return bounds


def _winsorize_apply(X: pd.DataFrame, bounds: dict[str, tuple[float, float]]) -> pd.DataFrame:
    out = X.copy()
    for c, (lo, hi) in bounds.items():
        if c in out.columns:
            out[c] = out[c].astype(float).clip(lower=lo, upper=hi)
    return out


def _impute_median(X: pd.DataFrame, medians: dict[str, float] | None = None) -> tuple[pd.DataFrame, dict[str, float]]:
    out = X.copy()
    used: dict[str, float] = {}
    for c in out.columns:
        if medians is not None and c in medians:
            med = medians[c]
        else:
            vals = out[c].astype(float)
            med = float(vals.median()) if vals.notna().any() else 0.0
        out[c] = out[c].astype(float).fillna(med)
        used[c] = med
    return out, used


def _fit_text_embeddings(reasoning_df: pd.DataFrame) -> tuple[TfidfVectorizer, TruncatedSVD, pd.DataFrame]:
    docs = reasoning_df["reasoning"].fillna("").tolist()
    vec = TfidfVectorizer(
        max_features=2000,
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
        stop_words="english",
    )
    M = vec.fit_transform(docs)
    n_comp = min(EMB_DIMS, M.shape[1] - 1) if M.shape[1] > 1 else 1
    svd = TruncatedSVD(n_components=n_comp, random_state=42)
    Z = svd.fit_transform(M)
    cols = [f"emb_{i}" for i in range(n_comp)]
    emb_df = pd.DataFrame(Z, columns=cols)
    emb_df["sim_id"] = reasoning_df["sim_id"].values
    emb_df["agent_id"] = reasoning_df["agent_id"].values
    # 若少于 EMB_DIMS，补 0 列
    for i in range(n_comp, EMB_DIMS):
        emb_df[f"emb_{i}"] = 0.0
    return vec, svd, emb_df[["sim_id", "agent_id"] + EMB_FEATURES]


def _apply_text_embeddings(vec: TfidfVectorizer, svd: TruncatedSVD, reasoning_df: pd.DataFrame) -> pd.DataFrame:
    if reasoning_df.empty:
        return pd.DataFrame(columns=["sim_id", "agent_id"] + EMB_FEATURES)
    docs = reasoning_df["reasoning"].fillna("").tolist()
    M = vec.transform(docs)
    Z = svd.transform(M)
    n_comp = Z.shape[1]
    cols = [f"emb_{i}" for i in range(n_comp)]
    out = pd.DataFrame(Z, columns=cols)
    out["sim_id"] = reasoning_df["sim_id"].values
    out["agent_id"] = reasoning_df["agent_id"].values
    for i in range(n_comp, EMB_DIMS):
        out[f"emb_{i}"] = 0.0
    return out[["sim_id", "agent_id"] + EMB_FEATURES]


def _join_features(struct_df: pd.DataFrame, emb_df: pd.DataFrame) -> pd.DataFrame:
    return struct_df.merge(emb_df, on=["sim_id", "agent_id"], how="left").fillna({c: 0.0 for c in EMB_FEATURES})


def _bootstrap_jaccard(X: np.ndarray, k: int, iters: int = 30, subsample: float = 0.8, seed: int = 42) -> float:
    rng = np.random.default_rng(seed)
    n = X.shape[0]
    m = max(int(n * subsample), k * 2)
    labels_full = KMeans(n_clusters=k, n_init=20, random_state=seed).fit_predict(X)
    full_clusters = [set(np.where(labels_full == c)[0]) for c in range(k)]
    jaccards = []
    for it in range(iters):
        idx = rng.choice(n, size=m, replace=False)
        sub_labels = KMeans(n_clusters=k, n_init=5, random_state=seed + it + 1).fit_predict(X[idx])
        # 计算重叠：把 sub_labels 映射回原 index
        sub_clusters = [set(idx[np.where(sub_labels == c)[0]].tolist()) for c in range(k)]
        # 贪心匹配最大化 Jaccard 和
        used = set()
        scores = []
        for fc in full_clusters:
            best = 0.0
            best_j = -1
            for j, sc in enumerate(sub_clusters):
                if j in used:
                    continue
                inter = len(fc & sc)
                union = len(fc | sc)
                if union > 0:
                    score = inter / union
                    if score > best:
                        best = score
                        best_j = j
            if best_j >= 0:
                used.add(best_j)
            scores.append(best)
        jaccards.append(float(np.median(scores)))
    return float(np.median(jaccards))


def fit_or_load_patterns(features_all: pd.DataFrame, refit: bool) -> dict:
    """在 rq1_panel 上拟合 K-means 模型，缓存到 _models/。"""
    paths = _model_paths()
    model_files = ["kmeans", "scaler", "pca", "winsor", "meta", "text_vec", "text_svd"]
    if not refit and all(paths[k].exists() for k in model_files):
        model = {
            "kmeans": joblib.load(paths["kmeans"]),
            "scaler": joblib.load(paths["scaler"]),
            "pca": joblib.load(paths["pca"]),
            "winsor": joblib.load(paths["winsor"]),
            "meta": json.loads(paths["meta"].read_text()),
        }
        if paths["text_vec"].exists():
            model["text_vec"] = joblib.load(paths["text_vec"])
            model["text_svd"] = joblib.load(paths["text_svd"])
        return model

    rq1 = features_all[features_all["suite"] == RQ1_SUITE].copy()
    if rq1.empty:
        raise RuntimeError("rq1_panel 上没有特征行，无法拟合模式。")

    X_struct = rq1[STRUCTURAL_FEATURES].copy()
    bounds = _winsorize_fit(X_struct)
    X_struct = _winsorize_apply(X_struct, bounds)
    X_struct, medians = _impute_median(X_struct)

    X_emb = rq1[EMB_FEATURES].copy()
    X_emb, emb_medians = _impute_median(X_emb)

    X = pd.concat([X_struct.reset_index(drop=True), X_emb.reset_index(drop=True)], axis=1)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X.values)

    # PCA 保留 90% 方差，上限 12
    pca = PCA(n_components=min(12, Xs.shape[1]))
    Xp_full = pca.fit_transform(Xs)
    cum = np.cumsum(pca.explained_variance_ratio_)
    n_keep = max(int(np.searchsorted(cum, 0.90) + 1), 2)
    n_keep = min(n_keep, Xp_full.shape[1])
    pca_keep = PCA(n_components=n_keep, random_state=42)
    Xp = pca_keep.fit_transform(Xs)

    # K 扫描
    sweep: list[dict] = []
    for k in [3, 4, 5, 6]:
        km = KMeans(n_clusters=k, n_init=20, random_state=42).fit(Xp)
        labels = km.labels_
        if len(set(labels)) < k:
            sweep.append({"k": k, "silhouette": -1.0, "jaccard": -1.0, "min_share": 0.0, "valid": False})
            continue
        silh = float(silhouette_score(Xp, labels))
        jac = _bootstrap_jaccard(Xp, k, iters=30, subsample=0.8)
        shares = np.bincount(labels) / len(labels)
        sweep.append({"k": k, "silhouette": silh, "jaccard": jac, "min_share": float(shares.min()), "valid": True})

    # 选最小满足门槛的 K，否则退化到最高 silhouette
    valid = [r for r in sweep if r["valid"] and r["silhouette"] >= 0.15 and r["jaccard"] >= 0.55 and r["min_share"] >= 0.06]
    if valid:
        chosen = min(valid, key=lambda r: r["k"])
    else:
        chosen = max([r for r in sweep if r["valid"]], key=lambda r: r["silhouette"]) if any(r["valid"] for r in sweep) else sweep[0]
    K = int(chosen["k"])

    km_final = KMeans(n_clusters=K, n_init=50, random_state=42).fit(Xp)

    # 给簇分配名字
    centers_in_orig = scaler.inverse_transform(pca_keep.inverse_transform(km_final.cluster_centers_))
    centers_df = pd.DataFrame(centers_in_orig, columns=X.columns)
    cluster_names = _assign_cluster_names(centers_df, K)

    meta = {
        "K": K,
        "sweep": sweep,
        "cluster_names": cluster_names,
        "winsor": {c: list(v) for c, v in bounds.items()},
        "medians": medians,
        "emb_medians": emb_medians,
        "n_components_kept": n_keep,
        "explained_variance": list(cum.tolist()),
        "feature_order": ALL_FEATURES,
        "fit_n_agents": int(len(rq1)),
        "version": V_PATTERN,
    }
    joblib.dump(km_final, paths["kmeans"])
    joblib.dump(scaler, paths["scaler"])
    joblib.dump(pca_keep, paths["pca"])
    joblib.dump(bounds, paths["winsor"])
    paths["meta"].write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    return {
        "kmeans": km_final,
        "scaler": scaler,
        "pca": pca_keep,
        "winsor": bounds,
        "meta": meta,
    }


def _assign_cluster_names(centers: pd.DataFrame, K: int) -> list[str]:
    """根据中心点 z-score 形态给簇取一个尽量可读的中文名。"""
    cores = centers[STRUCTURAL_FEATURES].copy()
    z = (cores - cores.mean()) / (cores.std(ddof=0) + 1e-9)
    scores = pd.DataFrame(index=range(K), columns=DEFAULT_PATTERN_NAME_POOL, dtype=float)
    for i, row in z.iterrows():
        scores.loc[i, "频繁挂撤型"] = (
            1.2 * row["share_CANCEL"]
            + 1.1 * row["cancel_to_submit_ratio"]
            + 0.4 * row["share_LIMIT"]
        )
        scores.loc[i, "信号反向型"] = (
            -1.2 * row["position_vs_midslope_match"]
            - 0.8 * row["belief_vs_price_corr"]
            + 0.3 * row["share_LIMIT"]
        )
        scores.loc[i, "信念锚定型"] = (
            -1.4 * row["belief_delta_mean_abs"]
            + 0.8 * row["share_HOLD"]
            - 0.5 * row["action_entropy"]
            - 0.4 * row["flip_count"]
        )
        scores.loc[i, "激进套利型"] = (
            1.0 * row["mean_size_pct_capital"]
            + 1.0 * row["max_size_pct_capital"]
            + 0.8 * row["terminal_exposure_ratio"]
            + 0.8 * row["final_pnl_norm"]
        )
        scores.loc[i, "观望保守型"] = (
            1.2 * row["share_HOLD"]
            - 0.8 * row["mean_size_pct_capital"]
            - 0.7 * row["final_pnl_norm"]
            + 0.4 * row["share_SPLITMERGE"]
        )
        scores.loc[i, "动量跟随型"] = (
            1.2 * row["position_vs_midslope_match"]
            + 0.8 * row["belief_vs_price_corr"]
            + 0.4 * row["terminal_exposure_ratio"]
        )

    # Greedy global assignment: choose the strongest remaining name/cluster pair
    # so cluster order from KMeans does not accidentally decide semantic names.
    names: list[str | None] = [None] * K
    used_clusters: set[int] = set()
    used_names: set[str] = set()
    candidates: list[tuple[float, int, str]] = []
    for i in range(K):
        for name in DEFAULT_PATTERN_NAME_POOL:
            candidates.append((float(scores.loc[i, name]), i, name))
    for _, i, name in sorted(candidates, key=lambda x: x[0], reverse=True):
        if i in used_clusters or name in used_names:
            continue
        names[i] = name
        used_clusters.add(i)
        used_names.add(name)
        if len(used_clusters) == K:
            break

    for i in range(K):
        if names[i] is not None:
            continue
        for cand in DEFAULT_PATTERN_NAME_POOL:
            if cand not in used_names:
                names[i] = cand
                used_names.add(cand)
                break
        if names[i] is None:
            names[i] = f"模式{i + 1}"
    return [str(x) for x in names]


def assign_patterns(features_all: pd.DataFrame, model: dict) -> pd.DataFrame:
    bounds = model["winsor"]
    scaler = model["scaler"]
    pca = model["pca"]
    km = model["kmeans"]
    meta = model["meta"]
    medians = meta["medians"]
    emb_medians = meta["emb_medians"]
    names = meta["cluster_names"]

    if features_all.empty:
        return pd.DataFrame()

    X_struct = features_all[STRUCTURAL_FEATURES].copy()
    X_struct = _winsorize_apply(X_struct, bounds)
    X_struct, _ = _impute_median(X_struct, medians=medians)
    X_emb = features_all[EMB_FEATURES].copy()
    X_emb, _ = _impute_median(X_emb, medians=emb_medians)
    X = pd.concat([X_struct.reset_index(drop=True), X_emb.reset_index(drop=True)], axis=1)
    Xs = scaler.transform(X.values)
    Xp = pca.transform(Xs)
    labels = km.predict(Xp)
    centers = km.cluster_centers_
    dists = np.linalg.norm(Xp[:, None, :] - centers[None, :, :], axis=2).min(axis=1)

    out = features_all[["sim_id", "agent_id", "suite", "config", "persona_type"]].copy()
    out["pattern_id"] = labels.astype(int)
    out["pattern_name"] = [names[int(c)] for c in labels]
    out["distance_to_centroid"] = dists.astype(float)
    return out


def write_per_run_patterns(patterns_all: pd.DataFrame, runs: list[Path]) -> None:
    sim_to_run = {}
    for run in runs:
        feat = _features_path(run)
        if feat.exists():
            sim_ids = pd.read_parquet(feat)["sim_id"].unique()
            for s in sim_ids:
                sim_to_run[str(s)] = run
    for sim_id, grp in patterns_all.groupby("sim_id"):
        run = sim_to_run.get(str(sim_id))
        if run is None:
            continue
        out_path = _patterns_path(run)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        grp.to_parquet(out_path, index=False)


# === 目录文档 ===============================================================
def write_pattern_catalog(model: dict, features_all: pd.DataFrame, patterns_all: pd.DataFrame, reasoning_all: pd.DataFrame) -> Path:
    meta = model["meta"]
    K = meta["K"]
    names = meta["cluster_names"]
    bounds = model["winsor"]
    scaler = model["scaler"]
    pca = model["pca"]
    km = model["kmeans"]
    medians = meta["medians"]
    emb_medians = meta["emb_medians"]

    rq1 = features_all[features_all["suite"] == RQ1_SUITE].copy().reset_index(drop=True)
    if rq1.empty:
        return OUT_ANALYSIS / "v15_behavioral_patterns.md"
    X_struct = _winsorize_apply(rq1[STRUCTURAL_FEATURES], bounds)
    X_struct, _ = _impute_median(X_struct, medians=medians)
    X_emb, _ = _impute_median(rq1[EMB_FEATURES], medians=emb_medians)
    X = pd.concat([X_struct.reset_index(drop=True), X_emb.reset_index(drop=True)], axis=1)
    Xs = scaler.transform(X.values)
    Xp = pca.transform(Xs)
    centers = km.cluster_centers_
    labels = km.predict(Xp)

    # 反投影中心到原始尺度
    centers_orig = scaler.inverse_transform(pca.inverse_transform(centers))
    centers_df = pd.DataFrame(centers_orig, columns=X.columns)
    pop_mean = X.mean()
    pop_std = X.std(ddof=0).replace(0, 1.0)
    centers_z = (centers_df - pop_mean) / pop_std

    lines = [
        "# v15 行为模式目录",
        "",
        f"模式数 K = {K}（在 rq1_panel 上拟合）。每个簇展示：top-5 |z| 特征 + 3 个最贴近中心的代表性 agent 的 reasoning 摘录。",
        "",
        "## K 选择诊断",
        "",
        "| K | silhouette | bootstrap Jaccard 中位 | 最小簇占比 | 有效 |",
        "|---:|---:|---:|---:|---:|",
    ]
    for r in meta["sweep"]:
        lines.append(
            f"| {r['k']} | {r['silhouette']:.3f} | {r['jaccard']:.3f} | {r['min_share']:.3f} | {'是' if r['valid'] else '否'} |"
        )
    lines.append("")

    # 计算每 agent 到各中心的距离，找 top-3
    dists = np.linalg.norm(Xp[:, None, :] - centers[None, :, :], axis=2)
    for c in range(K):
        order = np.argsort(dists[:, c])
        top = order[:3]
        z_row = centers_z.iloc[c]
        z_sorted = z_row.reindex(z_row.abs().sort_values(ascending=False).index)
        lines.append(f"## 模式 {c + 1}：{names[c]}")
        lines.append("")
        lines.append("**特征指纹（top-5 |z|）**：")
        lines.append("")
        lines.append("| 特征 | 中心 z 值 |")
        lines.append("|---|---:|")
        for fname in z_sorted.index[:5]:
            label = FEATURE_LABEL_ZH.get(fname, fname)
            lines.append(f"| {label} | {z_row[fname]:+.2f} |")
        lines.append("")
        lines.append("**代表性 agent reasoning 摘录**：")
        lines.append("")
        for i, idx in enumerate(top):
            sim_id = rq1.iloc[int(idx)]["sim_id"]
            aid = int(rq1.iloc[int(idx)]["agent_id"])
            sub = reasoning_all[(reasoning_all["sim_id"] == sim_id) & (reasoning_all["agent_id"] == aid)]
            text = sub["reasoning"].iloc[0] if not sub.empty else ""
            text = re.sub(r"\s+", " ", text)[:360]
            lines.append(f"- agent={aid} (sim {str(sim_id)[:8]}…)：{text}…")
        lines.append("")
        lines.append(f"建议中文名：**{names[c]}**（可在 `pattern_meta_{V_PATTERN}.json` 中调整）")
        lines.append("")

    out = OUT_ANALYSIS / "v15_behavioral_patterns.md"
    out.write_text("\n".join(lines))
    return out


# === 跨 run 汇总表 ==========================================================
def build_distribution_table(features_all: pd.DataFrame, patterns_all: pd.DataFrame, model: dict) -> pd.DataFrame:
    if features_all.empty:
        return pd.DataFrame()
    df = patterns_all.merge(
        features_all[["sim_id", "agent_id", "suite", "config", "final_pnl_norm"]],
        on=["sim_id", "agent_id"],
        how="left",
        suffixes=("", "_f"),
    )
    if "suite_f" in df.columns:
        df = df.drop(columns=[c for c in ("suite_f", "config_f") if c in df.columns])
    # 配置元信息
    rows = []
    for (suite, config, pattern_name), grp in df.groupby(["suite", "config", "pattern_name"]):
        rows.append({
            "suite": suite,
            "config": config,
            "pattern_name": pattern_name,
            "count": int(len(grp)),
            "median_final_pnl_norm": float(grp["final_pnl_norm"].median()),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    totals = out.groupby(["suite", "config"])["count"].transform("sum")
    out["share"] = out["count"] / totals
    out = out.sort_values(["suite", "config", "pattern_name"]).reset_index(drop=True)
    # 中文列名导出（程序内部继续保留英文键作为返回值供下游图表使用）
    out_zh = out.rename(columns={
        "suite": "实验套件",
        "config": "配置",
        "pattern_name": "行为模式",
        "count": "agent数量",
        "median_final_pnl_norm": "归一化收益中位数",
        "share": "占比",
    })
    out_zh.to_csv(OUT_TBL / "表_4_2_行为模式_分布_全部.csv", index=False)
    return out


def build_signature_table(model: dict) -> pd.DataFrame:
    meta = model["meta"]
    names = meta["cluster_names"]
    bounds = model["winsor"]
    scaler = model["scaler"]
    pca = model["pca"]
    km = model["kmeans"]
    centers_orig = scaler.inverse_transform(pca.inverse_transform(km.cluster_centers_))
    df = pd.DataFrame(centers_orig, columns=ALL_FEATURES)
    df.insert(0, "pattern_name", names)
    df.insert(0, "pattern_id", range(len(names)))
    rename_map = {"pattern_id": "模式编号", "pattern_name": "行为模式"}
    rename_map.update({c: FEATURE_LABEL_ZH.get(c, c) for c in ALL_FEATURES})
    df_zh = df.rename(columns=rename_map)
    df_zh.round(4).to_csv(OUT_TBL / "表_4_2_行为模式_特征指纹.csv", index=False)
    return df


# === 图表辅助 ==============================================================
def _config_scale_label(config: str) -> tuple[str, int]:
    m = re.search(r"_n(\d+)_", config)
    if m:
        return ("n", int(m.group(1)))
    m = re.search(r"_t(\d+)_", config)
    if m:
        return ("t", int(m.group(1)))
    return ("", 0)


def _draw_pattern_stack(ax, vals_by_pattern: dict[str, float], names: list[str], with_pct_text: bool = True) -> None:
    """在单个 ax 上绘制普通柱状图，并写百分比。"""
    vals = np.array([float(vals_by_pattern.get(pname, 0.0)) for pname in names], dtype=float)
    x = np.arange(len(names), dtype=float)
    colors = [PATTERN_PALETTE[i % len(PATTERN_PALETTE)] for i in range(len(names))]
    ax.bar(x, vals, color=colors, edgecolor="white", linewidth=0.35, width=0.72)
    if with_pct_text:
        for xi, v in zip(x, vals):
            if v >= 0.08:
                ax.text(xi, v + 0.018, f"{v*100:.0f}%", ha="center", va="bottom", fontsize=5.8)
    ax.set_xticks([])
    ax.set_xlim(-0.6, len(names) - 0.4)
    ax.set_ylim(0, 1.05)
    ax.grid(axis="y", alpha=0.2)


def _draw_belief_panel(ax, df: pd.DataFrame, truth: float, show_legend: bool = False) -> None:
    """画一个子图：累积成交笔数为 x，平均信念 vs 模拟市场价格。"""
    ax.fill_between(df["cum_trades"], df["p25_belief"], df["p75_belief"], color=BLUE, alpha=0.15, label="_nolegend_")
    ax.plot(df["cum_trades"], df["mean_belief"], color=BLUE, lw=1.1, marker="o", markersize=2.0, label="平均信念" if show_legend else "_nolegend_")
    ax.plot(df["cum_trades"], df["market_mid"], color=NEUTRAL_DARK, lw=0.9, alpha=0.82, label="模拟市场价格" if show_legend else "_nolegend_")
    if np.isfinite(truth):
        ax.axhline(truth, color=GREEN if truth == 1.0 else RED, ls="--", lw=0.7, label="_nolegend_")
    ax.axhline(0.5, color=NEUTRAL_MID, ls=":", lw=0.6, label="_nolegend_")
    ax.set_ylim(0, 1.0)


def _legend_handles_patterns(names: list[str]):
    return [plt.Rectangle((0, 0), 1, 1, color=PATTERN_PALETTE[i % len(PATTERN_PALETTE)]) for i in range(len(names))]


def _pattern_distribution_for(distribution: pd.DataFrame, suite: str, config_filter: str | None = None) -> dict[str, float]:
    sub = distribution[distribution["suite"] == suite]
    if config_filter is not None:
        sub = sub[sub["config"].str.contains(config_filter)]
    if sub.empty:
        return {}
    return dict(zip(sub["pattern_name"], sub["share"]))


def _belief_df_for_config(suite: str, config_substr: str) -> tuple[pd.DataFrame, float, str]:
    """返回 (belief 路径 df, truth, run path str)。找不到时 df 空。"""
    from _thesis_v15_common import truth_yes
    for run in latest_runs_of(suite):
        cfg = config_name(run)
        if config_substr in cfg:
            df = _belief_path_for_run(run)
            try:
                truth = truth_yes(cfg)
            except Exception:
                truth = float("nan")
            return df, truth, cfg
    return pd.DataFrame(), float("nan"), ""


# === 4-2-1 行为模式基线 =====================================================
def fig_4_2_1_baseline_patterns(distribution: pd.DataFrame, names: list[str]) -> None:
    """4-2-1: rq1_panel 总体行为模式占比，并另存特征指纹热图。

    原先把行为模式分布和高维热图挤在同一张图里，信息密度过高。这里拆成
    两张独立图：正文优先使用模式占比图，特征指纹图作为解释模式命名
    的辅助证据。
    """
    rq1 = distribution[distribution["suite"] == RQ1_SUITE]
    if rq1.empty:
        return
    agg = rq1.groupby("pattern_name")["count"].sum()
    total = float(agg.sum())
    shares = (agg / total).to_dict()

    fig, ax_bar = plt.subplots(figsize=fig_size(COL_DOUBLE_MM, 62))
    _draw_pattern_stack(ax_bar, shares, names)
    ax_bar.set_title("正常实验画像数量分布", fontsize=7.5)
    ax_bar.set_ylabel("画像占比")
    handles = _legend_handles_patterns(names)
    ax_bar.legend(
        handles, names, loc="center left", bbox_to_anchor=(1.01, 0.5),
        frameon=False, fontsize=6.5,
    )
    src = pd.DataFrame([{"行为模式": k, "占比": v, "agent数量": int(agg.get(k, 0))} for k, v in shares.items()])
    finalize_v15(fig, "4-2-1_微观_画像数量分布_正常实验", source_data=src, pad=0.6)

def build_signature_table_internal_only_for_baseline(model_meta_names: list[str]) -> pd.DataFrame:
    """从持久化模型重新生成中心点 dataframe，仅供 4-2-1 内部使用。"""
    paths = _model_paths()
    scaler = joblib.load(paths["scaler"])
    pca = joblib.load(paths["pca"])
    km = joblib.load(paths["kmeans"])
    centers_orig = scaler.inverse_transform(pca.inverse_transform(km.cluster_centers_))
    df = pd.DataFrame(centers_orig, columns=ALL_FEATURES)
    df.insert(0, "pattern_name", model_meta_names)
    return df


def fig_4_2_1_baseline_belief_gap() -> None:
    """4-2-1: rq1_panel 10 个市场的群体平均信念 vs 模拟市场价格。"""
    rq1_runs = latest_runs_of(RQ1_SUITE)
    if not rq1_runs:
        return
    fig, axes = plt.subplots(5, 2, figsize=fig_size(COL_DOUBLE_MM, 190), sharey=True)
    axes_flat = axes.ravel()
    from _thesis_v15_common import truth_yes
    src_rows: list[dict] = []
    for ax_idx, run in enumerate(rq1_runs[:10]):
        ax = axes_flat[ax_idx]
        df = _belief_path_for_run(run)
        cfg = config_name(run)
        title = RQ1_MARKET_TITLE.get(cfg, cfg)
        if df.empty:
            ax.axis("off")
            continue
        try:
            truth = truth_yes(cfg)
        except Exception:
            truth = float("nan")
        _draw_belief_panel(ax, df, truth, show_legend=(ax_idx == 0))
        ax.set_title(title, fontsize=6.4)
        for _, r in df.iterrows():
            src_rows.append({
                "市场": title, "config": cfg, "tick": int(r["tick_idx"]),
                "累积成交笔数": float(r["cum_trades"]),
                "平均信念": float(r["mean_belief"]),
                "模拟市场价格": float(r["market_mid"]),
                "差距": float(r["gap"]),
                "真实结局": float(truth) if np.isfinite(truth) else None,
            })
    for ax in axes[-1, :]:
        ax.set_xlabel("累积成交笔数")
    for ax in axes[:, 0]:
        ax.set_ylabel("YES 概率")
    handles, labels = axes_flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, fontsize=6.2, bbox_to_anchor=(0.5, 1.025))
    finalize_v15(fig, "4-2-1_微观_信念价格差距_正常实验", source_data=pd.DataFrame(src_rows), pad=0.7)


# === 4-2-2 规模扩展（c1） ===================================================
def fig_4_2_2_scale_patterns(distribution: pd.DataFrame, names: list[str]) -> None:
    """4-2-2: c1 行为模式占比，行=市场，列=智能体数量。"""
    ns = [10, 20, 50, 100]
    fig, axes = plt.subplots(len(BASE_MARKETS), len(ns), figsize=fig_size(COL_DOUBLE_MM, 110), sharey=True)
    src_rows: list[dict] = []
    for row_i, mkt in enumerate(BASE_MARKETS):
        suite = f"c1_{mkt}"
        for col_i, n in enumerate(ns):
            ax = axes[row_i, col_i]
            shares = _pattern_distribution_for(distribution, suite, f"_n{n}_")
            if not shares:
                ax.axis("off")
                continue
            _draw_pattern_stack(ax, shares, names)
            if row_i == 0:
                ax.set_title(f"n={n}", fontsize=7.5)
            if col_i == 0:
                ax.set_ylabel(f"{MARKET_LABEL[mkt]}\n画像占比", fontsize=7.2)
            for pname, v in shares.items():
                src_rows.append({"市场": MARKET_LABEL[mkt], "智能体数量": n, "行为模式": pname, "占比": float(v)})
    handles = _legend_handles_patterns(names)
    fig.legend(handles, names, loc="upper center", ncol=min(len(names), 5), frameon=False,
               fontsize=6.5, bbox_to_anchor=(0.5, 1.025))
    finalize_v15(fig, "4-2-2_微观_画像数量分布_规模扩展", source_data=pd.DataFrame(src_rows), pad=0.8)


def fig_4_2_2_scale_belief_gap() -> None:
    """4-2-2: c1 平均信念 vs 模拟市场价格，行=市场，列=智能体数量。"""
    ns = [10, 20, 50, 100]
    fig, axes = plt.subplots(len(BASE_MARKETS), len(ns), figsize=fig_size(COL_DOUBLE_MM, 110), sharex=False, sharey=True)
    src_rows: list[dict] = []
    for row_i, mkt in enumerate(BASE_MARKETS):
        suite = f"c1_{mkt}"
        for col_i, n in enumerate(ns):
            ax = axes[row_i, col_i]
            df, truth, cfg = _belief_df_for_config(suite, f"_n{n}_")
            if df.empty:
                ax.axis("off")
                continue
            _draw_belief_panel(ax, df, truth, show_legend=(row_i == 0 and col_i == 0))
            if row_i == 0:
                ax.set_title(f"n={n}", fontsize=7.5)
            if col_i == 0:
                ax.set_ylabel(f"{MARKET_LABEL[mkt]}\nYES 概率", fontsize=7.2)
            for _, r in df.iterrows():
                src_rows.append({"市场": MARKET_LABEL[mkt], "智能体数量": n, "tick": int(r["tick_idx"]),
                                 "累积成交笔数": float(r["cum_trades"]),
                                 "平均信念": float(r["mean_belief"]),
                                 "模拟市场价格": float(r["market_mid"]),
                                 "差距": float(r["gap"])})
    for ax in axes[-1, :]:
        ax.set_xlabel("累积成交笔数")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, fontsize=6.2, bbox_to_anchor=(0.5, 1.025))
    finalize_v15(fig, "4-2-2_微观_信念价格差距_规模扩展", source_data=pd.DataFrame(src_rows), pad=0.8)


# === 4-2-3 轮数扩展（c3） ===================================================
def fig_4_2_3_tick_patterns(distribution: pd.DataFrame, names: list[str]) -> None:
    ts = [10, 20, 50, 100]
    fig, axes = plt.subplots(len(BASE_MARKETS), len(ts), figsize=fig_size(COL_DOUBLE_MM, 110), sharey=True)
    src_rows: list[dict] = []
    for row_i, mkt in enumerate(BASE_MARKETS):
        suite = f"c3_{mkt}"
        for col_i, t in enumerate(ts):
            ax = axes[row_i, col_i]
            shares = _pattern_distribution_for(distribution, suite, f"_t{t}_")
            if not shares:
                ax.axis("off")
                continue
            _draw_pattern_stack(ax, shares, names)
            if row_i == 0:
                ax.set_title(f"t={t}", fontsize=7.5)
            if col_i == 0:
                ax.set_ylabel(f"{MARKET_LABEL[mkt]}\n画像占比", fontsize=7.2)
            for pname, v in shares.items():
                src_rows.append({"市场": MARKET_LABEL[mkt], "决策轮数": t, "行为模式": pname, "占比": float(v)})
    handles = _legend_handles_patterns(names)
    fig.legend(handles, names, loc="upper center", ncol=min(len(names), 5), frameon=False,
               fontsize=6.5, bbox_to_anchor=(0.5, 1.025))
    finalize_v15(fig, "4-2-3_微观_画像数量分布_决策轮数", source_data=pd.DataFrame(src_rows), pad=0.8)


def fig_4_2_3_tick_belief_gap() -> None:
    ts = [10, 20, 50, 100]
    fig, axes = plt.subplots(len(BASE_MARKETS), len(ts), figsize=fig_size(COL_DOUBLE_MM, 110), sharex=False, sharey=True)
    src_rows: list[dict] = []
    for row_i, mkt in enumerate(BASE_MARKETS):
        suite = f"c3_{mkt}"
        for col_i, t in enumerate(ts):
            ax = axes[row_i, col_i]
            df, truth, cfg = _belief_df_for_config(suite, f"_t{t}_")
            if df.empty:
                ax.axis("off")
                continue
            _draw_belief_panel(ax, df, truth, show_legend=(row_i == 0 and col_i == 0))
            if row_i == 0:
                ax.set_title(f"t={t}", fontsize=7.5)
            if col_i == 0:
                ax.set_ylabel(f"{MARKET_LABEL[mkt]}\nYES 概率", fontsize=7.2)
            for _, r in df.iterrows():
                src_rows.append({"市场": MARKET_LABEL[mkt], "决策轮数": t, "tick": int(r["tick_idx"]),
                                 "累积成交笔数": float(r["cum_trades"]),
                                 "平均信念": float(r["mean_belief"]),
                                 "模拟市场价格": float(r["market_mid"]),
                                 "差距": float(r["gap"])})
    for ax in axes[-1, :]:
        ax.set_xlabel("累积成交笔数")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, fontsize=6.2, bbox_to_anchor=(0.5, 1.025))
    finalize_v15(fig, "4-2-3_微观_信念价格差距_决策轮数", source_data=pd.DataFrame(src_rows), pad=0.8)


# === 4-2-4 消融实验（c4/c5/c6） =============================================
def _ablation_conditions(mod: dict) -> list[tuple[str, str]]:
    """返回 (suffix, label) 列表，按 baseline + ablations 顺序。"""
    return [(mod["baseline_suffix"], mod["baseline_label"])] + list(mod["ablation_suffixes"])


def fig_4_2_4_ablation_patterns(distribution: pd.DataFrame, names: list[str]) -> None:
    """4-2-4: 消融实验下行为模式占比，每个模块一行，每个市场各占若干列。
    布局：模块作为最外层行；每个模块下，市场×条件 在同一行展开。
    最终为 3 行 × max_cols 列，其中 c4 有 3 条件、c5/c6 有 2 条件。
    """
    max_cond = max(len(_ablation_conditions(m)) for m in ABLATION_MODULES)
    n_cols = max_cond * len(BASE_MARKETS)
    fig, axes = plt.subplots(len(ABLATION_MODULES), n_cols, figsize=fig_size(COL_DOUBLE_MM, 150), sharey=True)
    src_rows: list[dict] = []
    for row_i, mod in enumerate(ABLATION_MODULES):
        conds = _ablation_conditions(mod)
        col_idx = 0
        for mkt in BASE_MARKETS:
            suite = f"{mod['key']}_{mkt}"
            for suf, lbl in conds:
                ax = axes[row_i, col_idx]
                shares = _pattern_distribution_for(distribution, suite, f"_{suf}_")
                if shares:
                    _draw_pattern_stack(ax, shares, names)
                    title_str = f"{MARKET_LABEL[mkt]}·{lbl}" if col_idx % len(conds) == 0 or True else lbl
                    ax.set_title(f"{lbl}", fontsize=6.8)
                    for pname, v in shares.items():
                        src_rows.append({"模块": mod["label"], "市场": MARKET_LABEL[mkt], "条件": lbl,
                                         "行为模式": pname, "占比": float(v)})
                else:
                    ax.axis("off")
                col_idx += 1
            # 填充空白格（如果不同模块条件数不同）
            while col_idx < (BASE_MARKETS.index(mkt) + 1) * max_cond:
                axes[row_i, col_idx].axis("off")
                col_idx += 1
        # 在最左列写模块名 + 市场行标
        axes[row_i, 0].set_ylabel(f"{mod['label']}\n画像占比", fontsize=7)
        # 在每个市场段的中间加 x 标记（用 fig.text 太麻烦，改为在最上行写"市场名"）
        if row_i == 0:
            for mi, mkt in enumerate(BASE_MARKETS):
                mid_col = mi * max_cond + max_cond // 2
                axes[row_i, mid_col].annotate(MARKET_LABEL[mkt], xy=(0.5, 1.18),
                                              xycoords="axes fraction", ha="center", fontsize=8, fontweight="bold")
    handles = _legend_handles_patterns(names)
    fig.legend(handles, names, loc="upper center", ncol=min(len(names), 5), frameon=False,
               fontsize=6.5, bbox_to_anchor=(0.5, 1.03))
    finalize_v15(fig, "4-2-4_微观_画像数量分布_消融实验", source_data=pd.DataFrame(src_rows), pad=0.8)


def fig_4_2_4_ablation_belief_gap() -> None:
    """4-2-4: 消融实验下信念-价格差距。布局同 fig_4_2_4_ablation_patterns。"""
    max_cond = max(len(_ablation_conditions(m)) for m in ABLATION_MODULES)
    n_cols = max_cond * len(BASE_MARKETS)
    fig, axes = plt.subplots(len(ABLATION_MODULES), n_cols, figsize=fig_size(COL_DOUBLE_MM, 150), sharex=False, sharey=True)
    src_rows: list[dict] = []
    legend_set = False
    for row_i, mod in enumerate(ABLATION_MODULES):
        conds = _ablation_conditions(mod)
        col_idx = 0
        for mkt in BASE_MARKETS:
            suite = f"{mod['key']}_{mkt}"
            for suf, lbl in conds:
                ax = axes[row_i, col_idx]
                df, truth, cfg = _belief_df_for_config(suite, f"_{suf}_")
                if df.empty:
                    ax.axis("off")
                else:
                    _draw_belief_panel(ax, df, truth, show_legend=not legend_set)
                    legend_set = True
                    ax.set_title(f"{lbl}", fontsize=6.8)
                    for _, r in df.iterrows():
                        src_rows.append({"模块": mod["label"], "市场": MARKET_LABEL[mkt], "条件": lbl,
                                         "tick": int(r["tick_idx"]),
                                         "累积成交笔数": float(r["cum_trades"]),
                                         "平均信念": float(r["mean_belief"]),
                                         "模拟市场价格": float(r["market_mid"]),
                                         "差距": float(r["gap"])})
                col_idx += 1
            while col_idx < (BASE_MARKETS.index(mkt) + 1) * max_cond:
                axes[row_i, col_idx].axis("off")
                col_idx += 1
        axes[row_i, 0].set_ylabel(f"{mod['label']}\nYES 概率", fontsize=7)
        if row_i == 0:
            for mi, mkt in enumerate(BASE_MARKETS):
                mid_col = mi * max_cond + max_cond // 2
                axes[row_i, mid_col].annotate(MARKET_LABEL[mkt], xy=(0.5, 1.18),
                                              xycoords="axes fraction", ha="center", fontsize=8, fontweight="bold")
    for ax in axes[-1, :]:
        ax.set_xlabel("累积成交笔数")
    # 找一个非空 ax 取 legend
    for r in range(len(ABLATION_MODULES)):
        for c in range(n_cols):
            handles, labels = axes[r, c].get_legend_handles_labels()
            if handles:
                fig.legend(handles, labels, loc="upper center", ncol=2, fontsize=6.2, bbox_to_anchor=(0.5, 1.025))
                break
        else:
            continue
        break
    finalize_v15(fig, "4-2-4_微观_信念价格差距_消融实验", source_data=pd.DataFrame(src_rows), pad=0.8)


def _stacked_bar(ax, distribution: pd.DataFrame, names: list[str], x_labels: list[str], colors: list[str], y_label: str) -> None:
    bottom = np.zeros(len(x_labels))
    for i, pname in enumerate(names):
        vals = distribution.reindex(index=x_labels, columns=[pname]).fillna(0.0).values.flatten()
        ax.bar(x_labels, vals, bottom=bottom, color=colors[i % len(colors)], label=pname, edgecolor="white", linewidth=0.4)
        bottom = bottom + vals
    ax.set_ylim(0, 1.05)
    ax.set_ylabel(y_label)
    ax.grid(axis="y", alpha=0.25)


def figure_scale_distribution(distribution: pd.DataFrame, names: list[str], market: str) -> None:
    """图 4_2_微观_行为模式_规模分布_<market>。"""
    suite_c1 = f"c1_{market}"
    suite_c3 = f"c3_{market}"
    df = distribution[distribution["suite"].isin([suite_c1, suite_c3])].copy()
    if df.empty:
        return
    pivot = df.pivot_table(index=["suite", "config"], columns="pattern_name", values="share", aggfunc="sum").fillna(0.0)

    # 按 suite 排序 4 列
    def _sort_key(idx):
        return _config_scale_label(idx[1])[1]
    c1_idx = sorted([i for i in pivot.index if i[0] == suite_c1], key=_sort_key)
    c3_idx = sorted([i for i in pivot.index if i[0] == suite_c3], key=_sort_key)

    if not c1_idx and not c3_idx:
        return

    fig, axes = plt.subplots(2, 4, figsize=fig_size(COL_DOUBLE_MM, 110), sharey=True)
    row_specs = [(c1_idx, "n"), (c3_idx, "t")]
    for row_i, (idxs, axis_letter) in enumerate(row_specs):
        for col_i in range(4):
            ax = axes[row_i, col_i]
            ax.set_facecolor("white")
            if col_i < len(idxs):
                k = idxs[col_i]
                xnum = _config_scale_label(k[1])[1]
                vals = pivot.loc[[k]].iloc[0]
                bottom = 0.0
                for i, pname in enumerate(names):
                    v = float(vals.get(pname, 0.0))
                    ax.bar([0], [v], bottom=[bottom], color=PATTERN_PALETTE[i % len(PATTERN_PALETTE)], edgecolor="white", linewidth=0.4, width=0.7)
                    if v >= 0.05:
                        ax.text(0, bottom + v / 2, f"{v*100:.0f}%", ha="center", va="center", fontsize=7, color="white" if v >= 0.10 else NEUTRAL_DARK)
                    bottom += v
                ax.set_xticks([])
                ax.set_title(f"{axis_letter}={xnum}", fontsize=7.5)
                ax.set_ylim(0, 1.05)
                ax.grid(axis="y", alpha=0.25)
            else:
                ax.axis("off")
    axes[0, 0].set_ylabel("模式占比")
    axes[1, 0].set_ylabel("模式占比")
    handles = [plt.Rectangle((0, 0), 1, 1, color=PATTERN_PALETTE[i % len(PATTERN_PALETTE)]) for i in range(len(names))]
    fig.legend(handles, names, loc="upper center", ncol=min(len(names), 5), frameon=False, fontsize=6.5, bbox_to_anchor=(0.5, 1.025))
    fig.suptitle(MARKET_LABEL.get(market, market), y=1.08, fontsize=8)
    src = distribution[distribution["suite"].isin([suite_c1, suite_c3])][["suite", "config", "pattern_name", "share", "count", "median_final_pnl_norm"]].copy()
    src = src.rename(columns={
        "suite": "实验套件",
        "config": "配置",
        "pattern_name": "行为模式",
        "share": "占比",
        "count": "agent数量",
        "median_final_pnl_norm": "归一化收益中位数",
    })
    finalize_v15(fig, f"4_2_微观_行为模式_规模分布_{market}", source_data=src, pad=0.8)


def figure_ablation_distribution(distribution: pd.DataFrame, names: list[str]) -> None:
    """图 4_2_微观_行为模式_消融分布。"""
    fig, axes = plt.subplots(len(ABLATION_MODULES), 2, figsize=fig_size(COL_DOUBLE_MM, 140), sharey=True)
    src_rows: list[dict] = []
    for row_i, mod in enumerate(ABLATION_MODULES):
        for col_i, market in enumerate(BASE_MARKETS):
            ax = axes[row_i, col_i]
            ax.set_facecolor("white")
            suite = f"{mod['key']}_{market}"
            base_suffix = mod["baseline_suffix"]
            ab_suffixes = [s for s, _ in mod["ablation_suffixes"]]
            ab_labels = [lbl for _, lbl in mod["ablation_suffixes"]]
            order_suffixes = [base_suffix] + ab_suffixes
            order_labels = [mod["baseline_label"]] + ab_labels
            xs = []
            for suf, lbl in zip(order_suffixes, order_labels):
                cfg_rows = distribution[(distribution["suite"] == suite) & (distribution["config"].str.contains(f"_{suf}_"))]
                if cfg_rows.empty:
                    continue
                xs.append((suf, lbl, cfg_rows))
            if not xs:
                ax.axis("off")
                continue
            x_labels = [lbl for _, lbl, _ in xs]
            x_pos = np.arange(len(xs))
            bottom = np.zeros(len(xs))
            for i, pname in enumerate(names):
                vals = []
                for _, _, cfg_rows in xs:
                    sub = cfg_rows[cfg_rows["pattern_name"] == pname]
                    vals.append(float(sub["share"].sum()))
                vals_arr = np.array(vals)
                ax.bar(x_pos, vals_arr, bottom=bottom, color=PATTERN_PALETTE[i % len(PATTERN_PALETTE)], edgecolor="white", linewidth=0.4, width=0.7)
                for xi, vi in enumerate(vals_arr):
                    if vi >= 0.05:
                        ax.text(x_pos[xi], bottom[xi] + vi / 2, f"{vi*100:.0f}%", ha="center", va="center", fontsize=7, color="white" if vi >= 0.10 else NEUTRAL_DARK, fontweight="bold")
                bottom = bottom + vals_arr
            ax.set_xticks(x_pos)
            ax.set_xticklabels(x_labels, rotation=0, fontsize=7)
            for _, lbl, cfg_rows in xs:
                for _, row in cfg_rows.iterrows():
                    src_rows.append({
                        "消融模块": mod["label"],
                        "市场": MARKET_LABEL[market],
                        "条件": lbl,
                        "实验套件": row["suite"],
                        "配置": row["config"],
                        "行为模式": row["pattern_name"],
                        "agent数量": row["count"],
                        "占比": row["share"],
                        "归一化收益中位数": row["median_final_pnl_norm"],
                    })
            ax.set_ylim(0, 1.05)
            if col_i == 0:
                ax.set_ylabel(f"{mod['label']}\n模式占比", fontsize=7.5)
            if row_i == 0:
                ax.set_title(MARKET_LABEL[market], fontsize=7.5)
            ax.grid(axis="y", alpha=0.25)
    handles = [plt.Rectangle((0, 0), 1, 1, color=PATTERN_PALETTE[i % len(PATTERN_PALETTE)]) for i in range(len(names))]
    fig.legend(handles, names, loc="upper center", ncol=min(len(names), 5), frameon=False, fontsize=6.5, bbox_to_anchor=(0.5, 1.02))
    finalize_v15(fig, "4_2_微观_行为模式_消融分布", source_data=pd.DataFrame(src_rows), pad=0.8)


def figure_signature(signature_df: pd.DataFrame, names: list[str]) -> None:
    """图 4_2_微观_行为模式_特征指纹（z 值热图）。"""
    structural = STRUCTURAL_FEATURES
    df = signature_df[structural].copy()
    z = (df - df.mean()) / (df.std(ddof=0).replace(0, 1.0))
    fig, ax = plt.subplots(figsize=fig_size(COL_DOUBLE_MM, 130))
    norm = TwoSlopeNorm(vmin=float(z.values.min()), vcenter=0.0, vmax=float(z.values.max()))
    im = ax.imshow(z.values, aspect="auto", cmap="RdBu_r", norm=norm)
    ax.set_xticks(range(len(structural)))
    ax.set_xticklabels([FEATURE_LABEL_ZH.get(c, c) for c in structural], rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            zv = float(z.values[i, j])
            if abs(zv) >= 0.3:
                ax.text(j, i, f"{zv:+.1f}", ha="center", va="center", fontsize=6.5, color="white" if abs(zv) >= 1.0 else NEUTRAL_DARK)
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("z 值")
    sig_src = signature_df.copy()
    sig_rename = {"pattern_id": "模式编号", "pattern_name": "行为模式"}
    sig_rename.update({c: FEATURE_LABEL_ZH.get(c, c) for c in ALL_FEATURES})
    sig_src = sig_src.rename(columns=sig_rename)
    finalize_v15(fig, "4_2_微观_行为模式_特征指纹", source_data=sig_src, pad=0.6)


def _short_condition_label(suite: str, config: str) -> str:
    """把 (suite, config) 缩为简短中文标签，方便在收益矩阵列上显示。"""
    if suite == RQ1_SUITE:
        m = re.search(r"rq1_m(\d+)_", config)
        return f"rq1_m{m.group(1)}" if m else config
    if suite == "rq5_spacex":
        return "rq5_spacex"
    if suite.startswith("c1_") or suite.startswith("c3_"):
        mk = "以太坊" if "ethereum" in suite else "Robotaxi"
        m = re.search(r"_([nt])(\d+)_", config)
        if m:
            tag = "n" if m.group(1) == "n" else "t"
            return f"{mk} {tag}={m.group(2)}"
        return config
    if suite.startswith("c4_"):
        mk = "以太坊" if "ethereum" in suite else "Robotaxi"
        for key in ("concentrated", "natural", "uniform"):
            if key in config:
                return f"{mk} {'集中' if key == 'concentrated' else '自然' if key == 'natural' else '均匀'}"
    if suite.startswith("c5_"):
        mk = "以太坊" if "ethereum" in suite else "Robotaxi"
        return f"{mk} 思考{'开' if '_on_' in config else '关'}"
    if suite.startswith("c6_"):
        mk = "以太坊" if "ethereum" in suite else "Robotaxi"
        return f"{mk} 信念{'开' if 'belief_on' in config else '关'}"
    return config


def figure_payoff_matrix(distribution: pd.DataFrame, names: list[str]) -> None:
    """图 4_2_微观_行为模式_收益矩阵。"""
    df = distribution.copy()
    df["condition"] = df["suite"] + "::" + df["config"]
    pivot = df.pivot_table(index="pattern_name", columns="condition", values="median_final_pnl_norm", aggfunc="median")
    pivot = pivot.reindex(index=names)
    if pivot.empty:
        return
    fig, ax = plt.subplots(figsize=fig_size(COL_DOUBLE_MM, 150))
    vmax = float(np.nanmax(np.abs(pivot.values))) if pivot.values.size else 1.0
    if vmax < 1e-6:
        vmax = 1.0
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdBu_r", norm=norm)
    short_labels = []
    for c in pivot.columns:
        suite, config = c.split("::", 1)
        short_labels.append(_short_condition_label(suite, config))
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(short_labels, rotation=70, ha="right", fontsize=7)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    vals = pivot.values
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            v = vals[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=5.5, color="white" if abs(v) >= 0.5 * vmax else NEUTRAL_DARK)
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("归一化收益中位数")
    pay_src = pivot.reset_index().rename(columns={"pattern_name": "行为模式"})
    pay_src.columns = ["行为模式"] + short_labels
    finalize_v15(fig, "4_2_微观_行为模式_收益矩阵", source_data=pay_src, pad=0.6)


def figure_persistence(patterns_all: pd.DataFrame, names: list[str]) -> None:
    """图 4_2_微观_行为模式_市场间持续性。

    rq1_panel 跨 10 个市场，按钱包 persona_type（archetype）把同一类钱包
    在不同市场中归属的行为模式做配对计数，归一为"由模式 A 出发，配对落到模式 B"
    的概率（行归一）。对角线高 = 同钱包类型在不同市场表现稳定。
    """
    rq1 = patterns_all[patterns_all["suite"] == RQ1_SUITE].copy()
    if rq1.empty:
        return
    rq1 = rq1.dropna(subset=["persona_type"])
    rq1 = rq1[rq1["persona_type"].astype(str).str.len() > 0]
    if rq1.empty:
        return
    K = len(names)
    matrix = np.zeros((K, K), dtype=float)
    # 跨不同市场配对：只在不同 sim_id 之间配对，避免同一 sim 内部 self-pair
    for pt, grp in rq1.groupby("persona_type"):
        # 把每个市场内此 archetype 的 agent 当作一组，跨市场两两配对
        by_sim = {sid: g["pattern_name"].tolist() for sid, g in grp.groupby("sim_id")}
        sim_ids = sorted(by_sim)
        if len(sim_ids) < 2:
            continue
        for a_idx, sid_a in enumerate(sim_ids):
            for sid_b in sim_ids[a_idx + 1:]:
                for pa in by_sim[sid_a]:
                    for pb in by_sim[sid_b]:
                        if pa in names and pb in names:
                            ai, bi = names.index(pa), names.index(pb)
                            matrix[ai, bi] += 1
                            matrix[bi, ai] += 1
    row_sums = matrix.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    prob = matrix / row_sums

    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM, 110))
    vmax_prob = float(prob.max()) if prob.max() > 0 else 1.0
    im = ax.imshow(prob, aspect="auto", cmap="YlGnBu", vmin=0.0, vmax=vmax_prob)
    ax.set_xticks(range(K))
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(K))
    ax.set_yticklabels(names, fontsize=8)
    for i in range(K):
        for j in range(K):
            pv = prob[i, j]
            ax.text(j, i, f"{pv*100:.0f}%", ha="center", va="center", fontsize=7, color="white" if pv >= 0.5 * vmax_prob else NEUTRAL_DARK)
    cbar = fig.colorbar(im, ax=ax, shrink=0.85)
    cbar.set_label("跨市场配对概率")
    src = pd.DataFrame(prob, index=names, columns=names).reset_index().rename(columns={"index": "源模式"})
    finalize_v15(fig, "4_2_微观_行为模式_市场间持续性", source_data=src, pad=0.6)


# === 信念-价格差距图 =======================================================
def _belief_path_for_run(run: Path) -> pd.DataFrame:
    """按 tick 汇总 agent 平均信念与市场 mid，并把横轴换算为累积成交笔数。"""
    actions = load_actions(run)
    if actions.empty:
        return pd.DataFrame()
    belief = actions[actions["action_type"] == BELIEF_ACTION].copy()
    if belief.empty:
        return pd.DataFrame()
    belief["tick_idx"] = belief["tick_idx"].astype(int)
    belief["price"] = belief["price"].astype(float)
    belief["yes_mid_after"] = belief["yes_mid_after"].astype(float)
    grp = belief.groupby("tick_idx").agg(
        mean_belief=("price", "mean"),
        median_belief=("price", "median"),
        p25_belief=("price", lambda s: float(s.quantile(0.25))),
        p75_belief=("price", lambda s: float(s.quantile(0.75))),
        market_mid=("yes_mid_after", "mean"),
        n_agents=("agent_id", "nunique"),
    ).reset_index()
    grp["gap"] = grp["mean_belief"] - grp["market_mid"]
    # 把 tick 映射成累积成交笔数（沿用宏观图的口径）
    cum_map = cumulative_trade_map(run)
    grp["cum_trades"] = grp["tick_idx"].map(lambda t: float(cum_map.get(int(t), 0.0)))
    return grp


def figure_belief_vs_price(runs_index: dict[str, Path]) -> None:
    """图 4_2_微观_信念价格差距_rq1：rq1 10 个市场逐一展示信念均值、IQR
    与市场 mid 的同步走势，并标注真实结局。

    runs_index: {config_name: run_path} for rq1 markets.
    """
    rq1_runs = latest_runs_of(RQ1_SUITE)
    if not rq1_runs:
        return
    fig, axes = plt.subplots(5, 2, figsize=fig_size(COL_DOUBLE_MM, 190), sharex=False, sharey=True)
    axes_flat = axes.ravel()
    all_rows: list[dict] = []
    from _thesis_v15_common import truth_yes
    for ax_idx, run in enumerate(rq1_runs[:10]):
        ax = axes_flat[ax_idx]
        df = _belief_path_for_run(run)
        if df.empty:
            ax.axis("off")
            continue
        cfg = config_name(run)
        title = RQ1_MARKET_TITLE.get(cfg, cfg)
        try:
            truth = truth_yes(cfg)
        except Exception:
            truth = float("nan")
        ax.fill_between(df["cum_trades"], df["p25_belief"], df["p75_belief"], color=BLUE, alpha=0.15, label="_nolegend_")
        ax.plot(df["cum_trades"], df["mean_belief"], color=BLUE, lw=1.1, marker="o", markersize=2.1, label="平均信念")
        ax.plot(df["cum_trades"], df["market_mid"], color=NEUTRAL_DARK, lw=0.9, alpha=0.82, label="模拟市场价格")
        if np.isfinite(truth):
            ax.axhline(truth, color=GREEN if truth == 1.0 else RED, ls="--", lw=0.8, label="_nolegend_")
        ax.axhline(0.5, color=NEUTRAL_MID, ls=":", lw=0.65, label="_nolegend_")
        ax.set_title(title, fontsize=6.4)
        ax.set_ylim(0, 1.0)
        for _, r in df.iterrows():
            all_rows.append({
                "市场": title,
                "config": cfg,
                "tick": int(r["tick_idx"]),
                "累积成交笔数": float(r["cum_trades"]),
                "平均信念": float(r["mean_belief"]),
                "信念p25": float(r["p25_belief"]),
                "信念p75": float(r["p75_belief"]),
                "市场mid": float(r["market_mid"]),
                "差距": float(r["gap"]),
                "真实结局": float(truth) if np.isfinite(truth) else None,
            })
    for ax in axes[-1, :]:
        ax.set_xlabel("累积成交笔数")
    for ax in axes[:, 0]:
        ax.set_ylabel("YES 概率")
    handles, labels = axes_flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, fontsize=6.2, bbox_to_anchor=(0.5, 1.025))
    finalize_v15(fig, "4_2_微观_信念价格差距_rq1", source_data=pd.DataFrame(all_rows), pad=0.7)


def figure_belief_gap_summary() -> None:
    """图 4_2_微观_信念价格差距_汇总：把所有 v15 套件的信念-价格差距
    随时间分布汇总为一张图，左面板为 rq1 10 个市场的差距时间序列对齐，
    右面板为各消融条件下"|差|的时段均值"对照柱状图。
    """
    summary_rows: list[dict] = []
    suite_groups = [(RQ1_SUITE, "rq1"), *[(s, s) for s in SCALE_SUITES], *[(s, s) for s in ABLATION_SUITES]]
    for suite, _ in suite_groups:
        for run in latest_runs_of(suite):
            df = _belief_path_for_run(run)
            if df.empty:
                continue
            cfg = config_name(run)
            for _, r in df.iterrows():
                summary_rows.append({
                    "suite": suite,
                    "config": cfg,
                    "tick": int(r["tick_idx"]),
                    "cum_trades": float(r["cum_trades"]),
                    "mean_belief": float(r["mean_belief"]),
                    "market_mid": float(r["market_mid"]),
                    "gap": float(r["gap"]),
                })
    if not summary_rows:
        return
    summary = pd.DataFrame(summary_rows)

    fig, axes = plt.subplots(1, 2, figsize=fig_size(COL_DOUBLE_MM, 95))

    # 左：rq1 10 市场差距时间序列
    ax = axes[0]
    rq1_only = summary[summary["suite"] == RQ1_SUITE]
    palette = [BLUE, RED, GREEN, GOLD, VIOLET, TEAL, NEUTRAL_DARK, NEUTRAL_MID, "#8c564b", "#e377c2"]
    for i, (cfg, grp) in enumerate(rq1_only.groupby("config")):
        label = RQ1_MARKET_TITLE.get(cfg, cfg)
        ax.plot(grp["cum_trades"], grp["gap"], color=palette[i % len(palette)], lw=1.2, label=label, alpha=0.85)
    ax.axhline(0.0, color=NEUTRAL_DARK, lw=0.8, ls="--")
    ax.set_xlabel("累积成交笔数")
    ax.set_ylabel("平均信念 − 模拟市场价格")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=5.8, loc="lower right", ncol=2, frameon=False)
    panel_label(ax, "a")

    # 右：消融条件下"|差|的时段均值"
    ax = axes[1]
    cond_rows: list[dict] = []
    for mod in ABLATION_MODULES:
        for market in BASE_MARKETS:
            suite = f"{mod['key']}_{market}"
            base_suffix = mod["baseline_suffix"]
            ab_suffixes = [(s, l) for s, l in mod["ablation_suffixes"]]
            for suf, lbl in [(base_suffix, mod["baseline_label"])] + ab_suffixes:
                sub = summary[(summary["suite"] == suite) & (summary["config"].str.contains(f"_{suf}_"))]
                if sub.empty:
                    continue
                cond_rows.append({
                    "模块": mod["label"],
                    "市场": MARKET_LABEL[market],
                    "条件": lbl,
                    "|差|均值": float(sub["gap"].abs().mean()),
                })
    cond = pd.DataFrame(cond_rows)
    if not cond.empty:
        cond["x"] = cond["模块"] + " · " + cond["市场"]
        pivot_cond = cond.pivot_table(index=["x"], columns="条件", values="|差|均值", aggfunc="mean")
        pivot_cond = pivot_cond.fillna(0.0)
        x_pos = np.arange(len(pivot_cond.index))
        n_cond = len(pivot_cond.columns)
        width = 0.8 / max(n_cond, 1)
        for i, condition in enumerate(pivot_cond.columns):
            offsets = (i - (n_cond - 1) / 2) * width
            ax.bar(x_pos + offsets, pivot_cond[condition].values, width=width, label=condition,
                   color=palette[i % len(palette)], edgecolor="white", linewidth=0.4)
            for xi, v in enumerate(pivot_cond[condition].values):
                if v > 0:
                    ax.text(x_pos[xi] + offsets, v + 0.005, f"{v:.2f}", ha="center", va="bottom", fontsize=5.5)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(pivot_cond.index, rotation=30, ha="right", fontsize=6.5)
        ax.set_ylabel("|信念 − 模拟市场价格| 时段均值")
        ax.legend(fontsize=5.8, loc="upper left", ncol=1, frameon=False)
        ax.grid(axis="y", alpha=0.25)
    panel_label(ax, "b")

    finalize_v15(fig, "4_2_微观_信念价格差距_汇总", source_data=summary, pad=0.6)


# === 入口 ==================================================================
def run(refit: bool = False) -> None:
    runs = all_v15_runs()
    if not runs:
        print("没有可用 v15 run，跳过行为模式分析。")
        return

    print(f"[patterns] 扫描 {len(runs)} 个 run 生成 per-agent 特征 ...")
    struct_all, reasoning_all = compute_or_load_features(runs, force=False)
    if struct_all.empty:
        print("[patterns] 结构化特征为空，终止。")
        return

    paths = _model_paths()
    # reasoning 嵌入：拟合一次（仅用 rq1_panel 上有 reasoning 的行），其它 suite 走 transform
    rq1_reasoning = reasoning_all[reasoning_all["suite"] == RQ1_SUITE] if not reasoning_all.empty else pd.DataFrame()
    if refit or not paths["text_vec"].exists():
        if rq1_reasoning.empty:
            print("[patterns] rq1 reasoning 缺失，回退到全样本拟合 reasoning 嵌入。")
            base = reasoning_all
        else:
            base = rq1_reasoning
        if base.empty:
            text_vec = None
            text_svd = None
            emb_df_rq1 = pd.DataFrame(columns=["sim_id", "agent_id"] + EMB_FEATURES)
        else:
            text_vec, text_svd, emb_df_rq1 = _fit_text_embeddings(base.reset_index(drop=True))
            joblib.dump(text_vec, paths["text_vec"])
            joblib.dump(text_svd, paths["text_svd"])
    else:
        text_vec = joblib.load(paths["text_vec"])
        text_svd = joblib.load(paths["text_svd"])

    if text_vec is not None and not reasoning_all.empty:
        emb_all = _apply_text_embeddings(text_vec, text_svd, reasoning_all.reset_index(drop=True))
    else:
        emb_all = pd.DataFrame(columns=["sim_id", "agent_id"] + EMB_FEATURES)

    features_all = _join_features(struct_all, emb_all)

    print("[patterns] 拟合或加载模式模型 ...")
    model = fit_or_load_patterns(features_all, refit=refit)

    print("[patterns] 应用模式到所有 run ...")
    patterns_all = assign_patterns(features_all, model)
    if not patterns_all.empty:
        write_per_run_patterns(patterns_all, runs)

    print("[patterns] 渲染分布表、特征指纹表、目录 markdown ...")
    distribution = build_distribution_table(features_all, patterns_all, model)
    signature = build_signature_table(model)
    write_pattern_catalog(model, features_all, patterns_all, reasoning_all)

    names = model["meta"]["cluster_names"]
    print("[patterns] 渲染 4-2-1 正常实验画像数量分布 + 信念价格差距 ...")
    fig_4_2_1_baseline_patterns(distribution, names)
    fig_4_2_1_baseline_belief_gap()
    print("[patterns] 渲染 4-2-2 规模扩展画像数量分布 + 信念价格差距 ...")
    fig_4_2_2_scale_patterns(distribution, names)
    fig_4_2_2_scale_belief_gap()
    print("[patterns] 渲染 4-2-3 决策轮数画像数量分布 + 信念价格差距 ...")
    fig_4_2_3_tick_patterns(distribution, names)
    fig_4_2_3_tick_belief_gap()
    print("[patterns] 渲染 4-2-4 消融实验画像数量分布 + 信念价格差距 ...")
    fig_4_2_4_ablation_patterns(distribution, names)
    fig_4_2_4_ablation_belief_gap()
    print("[patterns] 完成。")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--refit", action="store_true", help="强制重新拟合行为模式模型")
    args = parser.parse_args()
    run(refit=args.refit)
