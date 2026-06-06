"""Shared helpers for the v15 thesis figure pipeline.

Centralizes:
  - palette, action constants, market metadata
  - run discovery (runs_of / latest_runs_of / grouped)
  - per-run metric computation (load_actions/fills/positions, metrics)
  - real-market trade path loading and alignment helpers
  - drawing helpers (panel_label, integer_xaxis, draw_market_cutoff)
  - ``finalize_v15`` — like _thesis_style.finalize but writes every format
    into its own subfolder (``figures/{pdf,png,svg,tiff}/``).

The three section scripts (4_1 macro, 4_2 micro, 4_3 validation) all import
from this module so the orchestrator can call them independently while
keeping a single source of truth.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

from _thesis_style import (
    BLUE,
    GREEN,
    RED,
    TEAL,
    VIOLET,
    GOLD,
    NEUTRAL_LIGHT,
    NEUTRAL_MID,
    NEUTRAL_DARK,
    apply_style,
    apply_text_fonts,
    fig_size,
    fig_size_vstack,
    panel_label,
    COL_DOUBLE_MM,
    COL_SINGLE_MM,
)


apply_style()

ROOT = Path(__file__).resolve().parent.parent
V15 = ROOT / "output" / "v15"
OUT_BASE = ROOT / "docs" / "v15"
OUT_FIG = OUT_BASE / "figures"
OUT_TBL = OUT_BASE / "tables"
OUT_ANALYSIS = OUT_BASE / "analysis"
FIG_FORMATS = ("png", "svg", "pdf", "tiff")
for _fmt in FIG_FORMATS:
    (OUT_FIG / _fmt).mkdir(parents=True, exist_ok=True)
(OUT_FIG / "data").mkdir(parents=True, exist_ok=True)
OUT_TBL.mkdir(parents=True, exist_ok=True)
OUT_ANALYSIS.mkdir(parents=True, exist_ok=True)

BASE_MARKETS = ("ethereum", "robotaxi")
MARKET_LABEL = {
    "ethereum": "以太坊 5000 美元",
    "robotaxi": "特斯拉 Robotaxi",
    "spacex": "SpaceX 助推器回收",
}
RQ1_MARKET_TITLE = {
    "rq1_m01_s0": "特斯拉10月底前推出无监督FSD",
    "rq1_m02_s0": "特朗普周一前部署国民警卫队",
    "rq1_m03_s0": "最高法院裁定支持特朗普关税",
    "rq1_m04_s0": "Katy Perry与Justin Trudeau关系确认",
    "rq1_m05_s0": "比特币7月触及12.5万美元",
    "rq1_m06_s0": "2025年底比特币高于10万美元",
    "rq1_m07_s0": "MicroStrategy继续购买比特币",
    "rq1_m08_s0": "NFL酋长对巨人比赛结果",
    "rq1_m09_s0": "NFL乌鸦对比尔比赛结果",
    "rq1_m10_s0": "Lord Miles完成40天禁食挑战",
    "rq5_spacex_s0": "SpaceX星舰第11次试飞助推器回收",
}
MARKET_COLOR = {"ethereum": TEAL, "robotaxi": BLUE, "spacex": VIOLET}
ACTION_ORDER = ["LIMIT", "MARKET", "CANCEL", "HOLD", "SPLIT", "MERGE"]
ACTION_COLOR = {
    "LIMIT": BLUE,
    "MARKET": GREEN,
    "CANCEL": RED,
    "HOLD": NEUTRAL_MID,
    "SPLIT": TEAL,
    "MERGE": VIOLET,
}
TRADING_ACTIONS = {"LIMIT", "MARKET", "CANCEL", "HOLD", "SPLIT", "MERGE"}
ACTIVE_TRADE_ACTIONS = {"LIMIT", "MARKET"}

# Ablation module definitions for 4-1-4 / 4-2-4.
# Each entry: human label + baseline config suffix + list of ablation suffixes.
ABLATION_MODULES = [
    {
        "key": "c4",
        "label": "画像分布",
        "baseline_suffix": "natural",
        "ablation_suffixes": [
            ("concentrated", "集中分布"),
            ("uniform", "均匀分布"),
        ],
        "baseline_label": "经验自然分布",
    },
    {
        "key": "c5",
        "label": "思考模式",
        "baseline_suffix": "on",
        "ablation_suffixes": [("off", "关闭思考")],
        "baseline_label": "开启思考",
    },
    {
        "key": "c6",
        "label": "信念更新工具",
        "baseline_suffix": "belief_on",
        "ablation_suffixes": [("belief_off", "关闭信念更新")],
        "baseline_label": "开启信念更新",
    },
]


# --- run discovery ------------------------------------------------------------
def config_name(run: Path) -> str:
    parts = run.name.split("-")
    return "-".join(parts[1:-2])


def market_title_for(config: str) -> str:
    return RQ1_MARKET_TITLE.get(config, config)


def safe_fig_name(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|.\s]+', "_", text).strip("_")


def runs_of(suite: str) -> list[Path]:
    base = V15 / suite
    if not base.exists():
        return []
    runs = []
    for run in sorted(base.glob("2026*/")):
        if (run / "raw" / "agent_actions.parquet").exists() and (run / "meta.json").exists():
            runs.append(run)
    return runs


def latest_runs_of(suite: str) -> list[Path]:
    by_config: dict[str, Path] = {}
    for run in runs_of(suite):
        by_config[config_name(run)] = run
    return [by_config[k] for k in sorted(by_config)]


# --- priors & truth -----------------------------------------------------------
def prior_for(slug: str) -> dict:
    return json.loads((ROOT / f"data/priors_{slug}.json").read_text())


def truth_yes(slug: str) -> float:
    pri = prior_for(slug)
    wi = pri.get("winning_idx")
    if wi is None or wi < 0:
        return float("nan")
    return 1.0 if int(wi) == 0 else 0.0


def outcome_label(truth: float) -> str:
    if math.isnan(truth):
        return "未结算"
    return "YES 结局=1.00" if truth == 1.0 else "NO 结局，YES=0.00"


def market_key_from_slug(slug: str) -> str:
    if "ethereum" in slug:
        return "ethereum"
    if "tesla" in slug or "robotaxi" in slug:
        return "robotaxi"
    if "spacex" in slug or "starship" in slug:
        return "spacex"
    return "other"


# --- run-level loaders + metrics ---------------------------------------------
def load_actions(run: Path) -> pd.DataFrame:
    return pd.read_parquet(run / "raw" / "agent_actions.parquet")


def load_fills(run: Path) -> pd.DataFrame:
    return pd.read_parquet(run / "raw" / "agent_fills.parquet")


def load_positions(run: Path) -> pd.DataFrame:
    return pd.read_parquet(run / "raw" / "agent_positions.parquet")


def yes_mid_path(actions: pd.DataFrame) -> pd.Series:
    mids = actions.dropna(subset=["yes_mid_after"]).groupby("tick_idx")["yes_mid_after"].last()
    return mids.astype(float)


def metrics(run: Path) -> dict:
    meta = json.loads((run / "meta.json").read_text())
    summ = json.loads((run / "analysis" / "summary.json").read_text())
    actions = load_actions(run)
    fills = load_fills(run)
    positions = load_positions(run)
    mids = yes_mid_path(actions)
    slug = meta["config"]["market"]["slug"]
    truth = truth_yes(slug)
    n_agents = int(summ["n_agents"])
    n_ticks = int(summ["n_ticks"])
    n_fills = int(len(fills))
    notional = float(fills["notional"].sum()) if len(fills) else 0.0
    decision_actions = actions[actions["action_type"].isin(TRADING_ACTIONS)]
    active_trade_actions = actions[actions["action_type"].isin(ACTIVE_TRADE_ACTIONS)]
    final_pos = positions.sort_values("tick_idx").groupby("agent_id").tail(1).copy()
    final_pnl = final_pos["realized_pnl"].astype(float) + final_pos["unrealized_pnl"].astype(float)
    start_mid = float(mids.iloc[0]) if len(mids) else float("nan")
    end_mid = float(mids.iloc[-1]) if len(mids) else float("nan")
    if math.isnan(truth):
        direction_score = float("nan")
        distance_to_truth = float("nan")
    else:
        direction = 1.0 if truth == 1.0 else -1.0
        direction_score = (end_mid - start_mid) * direction
        distance_to_truth = abs(end_mid - truth)
    action_mix = (
        decision_actions["action_type"].value_counts(normalize=True).mul(100).to_dict()
        if len(decision_actions)
        else {}
    )
    return {
        "run": run,
        "config": config_name(run),
        "slug": slug,
        "market_key": market_key_from_slug(slug),
        "n_agents": n_agents,
        "n_ticks": n_ticks,
        "truth": truth,
        "truth_label": outcome_label(truth),
        "signal_mu": float(meta["priors_summary"]["signal_mu"]),
        "start_mid": start_mid,
        "end_mid": end_mid,
        "drift": end_mid - start_mid,
        "direction_score": direction_score,
        "distance_to_truth": distance_to_truth,
        "volatility": float(mids.diff().dropna().std()) if len(mids) > 1 else 0.0,
        "max_abs_step": float(mids.diff().abs().max()) if len(mids) > 1 else 0.0,
        "n_fills": n_fills,
        "notional": notional,
        "fills_per_agent_tick": n_fills / max(n_agents * n_ticks, 1),
        "notional_per_agent": notional / max(n_agents, 1),
        "active_trade_fill_rate": n_fills / max(len(active_trade_actions), 1),
        "cancel_per_fill": int((actions["action_type"] == "CANCEL").sum()) / max(n_fills, 1),
        "price_response_per_1k_notional": abs(end_mid - start_mid) / max(notional / 1000.0, 1e-9),
        "pnl_mean": float(summ["pnl_mean"]),
        "pnl_std": float(final_pnl.std(ddof=1)) if len(final_pnl) > 1 else 0.0,
        "pnl_spread": float(final_pnl.max() - final_pnl.min()) if len(final_pnl) else 0.0,
        "mids": mids,
        "action_mix": action_mix,
    }


def grouped(suite: str, pattern: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for run in latest_runs_of(suite):
        m = re.search(pattern, config_name(run))
        if not m:
            continue
        out.setdefault(m.group(1), []).append(metrics(run))
    return out


# --- plotting helpers --------------------------------------------------------
def integer_xaxis(ax) -> None:
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))


def result_label(r: dict) -> str:
    if math.isnan(float(r["direction_score"])):
        return "未结算"
    return "朝真实结局" if float(r["direction_score"]) > 0 else "背离真实结局"


def result_color(r: dict) -> str:
    if math.isnan(float(r["direction_score"])):
        return NEUTRAL_DARK
    return GREEN if float(r["direction_score"]) > 0 else RED


def path_rows(r: dict, label: str) -> list[dict]:
    mids = r["mids"]
    if not len(mids):
        return []
    denom = max(len(mids) - 1, 1)
    return [
        {
            "series": label,
            "config": r["config"],
            "market": r["market_key"],
            "tick": int(t),
            "frac": float(i / denom),
            "yes_mid": float(v),
            "truth": r["truth"],
        }
        for i, (t, v) in enumerate(mids.items())
    ]


# --- real-market trade-path helpers ------------------------------------------
def try_real_trade_path(slug: str, max_points: int = 80) -> pd.DataFrame:
    try:
        from data.query.trades import get_trades
    except Exception:
        return pd.DataFrame()
    pri = prior_for(slug)
    since = pri.get("market_open_ts")
    until = None
    if pri.get("end_date_iso"):
        try:
            until = int(datetime.fromisoformat(pri["end_date_iso"].replace("Z", "+00:00")).timestamp())
        except ValueError:
            until = None
    if since is not None and until is not None and until <= since:
        until = None
    try:
        rows = get_trades(pri["condition_id"], since_ts=since, until_ts=until)
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["trade_time", "outcome_index", "price", "size", "wallet"])
    df["ts"] = pd.to_datetime(df["trade_time"], utc=True)
    df["yes_price"] = np.where(
        df["outcome_index"].astype(int) == 0,
        df["price"].astype(float),
        1.0 - df["price"].astype(float),
    )
    df["notional"] = df["yes_price"] * df["size"].astype(float)
    df = df.sort_values("ts")
    df["real_cum_trades"] = np.arange(1, len(df) + 1)
    if len(df) > max_points:
        df["bin"] = pd.cut(np.arange(len(df)), bins=max_points, labels=False)
        out = df.groupby("bin", as_index=False).agg(
            ts=("ts", "last"),
            yes_price=("yes_price", "mean"),
            volume=("notional", "sum"),
            real_cum_trades=("real_cum_trades", "max"),
        )
    else:
        out = df.rename(columns={"notional": "volume"})[["ts", "yes_price", "volume", "real_cum_trades"]]
    denom = max(len(out) - 1, 1)
    out["frac"] = np.arange(len(out)) / denom
    out["slug"] = slug
    return out


def real_path_for_plot(r: dict, sim_df: pd.DataFrame) -> pd.DataFrame:
    real = try_real_trade_path(r["slug"])
    if real.empty:
        return real
    real = real.copy()
    max_tick = float(max(sim_df["tick"].max(), 1))
    real["mapped_tick"] = real["frac"] * max_tick
    real["config"] = r["config"]
    real["market_title"] = market_title_for(r["config"])
    real["truth"] = r["truth"]
    return real


def split_terminal_settlement(real: pd.DataFrame, truth: float, x_col: str) -> tuple[pd.DataFrame, float | None]:
    if real.empty or math.isnan(float(truth)):
        return real, None
    prices = real["yes_price"].astype(float).to_numpy()
    if float(truth) == 1.0:
        terminal = prices >= 0.99
    else:
        terminal = prices <= 0.01
    if not terminal[-1]:
        return real, None
    first_terminal = len(terminal) - 1
    while first_terminal > 0 and terminal[first_terminal - 1]:
        first_terminal -= 1
    cutoff_x = float(real.iloc[first_terminal][x_col])
    plotted = real.iloc[:first_terminal].copy()
    return plotted, cutoff_x


def draw_market_cutoff(ax, cutoff_x: float | None, label: str = "事件结束") -> None:
    if cutoff_x is None:
        return
    ax.axvline(cutoff_x, color=NEUTRAL_DARK, ls="-.", lw=0.8, alpha=0.75, label=label)


def real_path_source_rows(real: pd.DataFrame) -> list[dict]:
    if real.empty:
        return []
    return [
        {
            "series": "真实市场YES成交价",
            "config": row["config"],
            "market_title": row["market_title"],
            "tick": float(row["mapped_tick"]),
            "frac": float(row["frac"]),
            "yes_mid": float(row["yes_price"]),
            "truth": float(row["truth"]),
            "ts": row["ts"],
            "volume": float(row["volume"]),
            "slug": row["slug"],
        }
        for _, row in real.iterrows()
    ]


def simulated_trade_count_path(r: dict) -> pd.DataFrame:
    data = pd.DataFrame(path_rows(r, "模拟YES中间价"))
    if data.empty:
        return data
    fills = load_fills(r["run"])
    if fills.empty or "tick_idx" not in fills.columns:
        data["cum_trades"] = data["tick"].astype(float)
        data["trade_progress"] = data["frac"]
        return data
    fill_counts = fills.groupby("tick_idx").size()
    tick_counts = data["tick"].map(fill_counts).fillna(0).astype(int)
    data["cum_trades"] = tick_counts.cumsum().astype(float)
    start = data.iloc[[0]].copy()
    start["cum_trades"] = 0.0
    start["trade_progress"] = 0.0
    data = pd.concat([start, data], ignore_index=True)
    total = float(max(data["cum_trades"].max(), 1.0))
    data["trade_progress"] = data["cum_trades"] / total
    return data


def cumulative_trade_map(run: Path) -> dict[int, float]:
    actions = load_actions(run)
    ticks = sorted(actions["tick_idx"].dropna().astype(int).unique())
    fills = load_fills(run)
    fill_counts = fills.groupby("tick_idx").size() if not fills.empty and "tick_idx" in fills.columns else pd.Series(dtype=float)
    cum = 0.0
    out: dict[int, float] = {}
    for tick in ticks:
        cum += float(fill_counts.get(tick, 0.0))
        out[int(tick)] = cum
    return out


def micro_trade_count_behavior_path(r: dict, series_label: str) -> pd.DataFrame:
    actions = load_actions(r["run"]).sort_values("tick_idx")
    fills = load_fills(r["run"])
    ticks = pd.Index(sorted(actions["tick_idx"].dropna().astype(int).unique()), name="tick")
    if ticks.empty:
        return pd.DataFrame()
    active = actions[actions["action_type"].isin(ACTIVE_TRADE_ACTIONS)].groupby("tick_idx").size()
    cancels = actions[actions["action_type"] == "CANCEL"].groupby("tick_idx").size()
    fill_counts = fills.groupby("tick_idx").size() if not fills.empty and "tick_idx" in fills.columns else pd.Series(dtype=float)
    df = pd.DataFrame({"tick": ticks.to_numpy()})
    df["active_actions"] = df["tick"].map(active).fillna(0).astype(float)
    df["cancel_actions"] = df["tick"].map(cancels).fillna(0).astype(float)
    df["fills"] = df["tick"].map(fill_counts).fillna(0).astype(float)
    df["cum_trades"] = df["fills"].cumsum()
    df["cum_active_actions"] = df["active_actions"].cumsum()
    df["cum_cancel_actions"] = df["cancel_actions"].cumsum()
    denom = df["cum_active_actions"].replace(0, np.nan)
    df["execution_rate"] = (df["cum_trades"] / denom).fillna(0.0)
    df["cancel_per_trade"] = (df["cum_cancel_actions"] / df["cum_trades"].replace(0, np.nan)).fillna(0.0)
    df["series"] = series_label
    df["config"] = r["config"]
    df["market"] = r["market_key"]
    df["market_title"] = MARKET_LABEL.get(r["market_key"], r["market_key"])
    return df.drop_duplicates("cum_trades", keep="last")


def real_trade_count_path(r: dict, sim_trade_df: pd.DataFrame) -> pd.DataFrame:
    real = try_real_trade_path(r["slug"])
    if real.empty or sim_trade_df.empty:
        return real
    real = real.copy()
    total_sim_trades = float(max(sim_trade_df["cum_trades"].max(), 1.0))
    real["cum_trades"] = real["frac"] * total_sim_trades
    real["trade_progress"] = real["frac"]
    real["config"] = r["config"]
    real["market_title"] = market_title_for(r["config"])
    real["truth"] = r["truth"]
    return real


def real_actual_trade_count_path(r: dict, max_points: int = 120) -> pd.DataFrame:
    real = try_real_trade_path(r["slug"], max_points=max_points)
    if real.empty:
        return real
    real = real.copy()
    real["cum_trades"] = real["real_cum_trades"].astype(float)
    real["trade_progress"] = real["frac"]
    real["config"] = r["config"]
    real["market_title"] = market_title_for(r["config"])
    real["truth"] = r["truth"]
    return real


def trade_count_source_data(sim_trade_df: pd.DataFrame, real: pd.DataFrame) -> pd.DataFrame:
    sim_rows = []
    for _, row in sim_trade_df.iterrows():
        sim_rows.append({
            "series": "模拟市场价格",
            "config": row["config"],
            "market_title": market_title_for(row["config"]),
            "cum_trades": float(row["cum_trades"]),
            "trade_progress": float(row["trade_progress"]),
            "yes_price": float(row["yes_mid"]),
            "truth": float(row["truth"]),
            "tick": int(row["tick"]),
        })
    real_rows = []
    if not real.empty:
        for _, row in real.iterrows():
            real_rows.append({
                "series": "真实市场价格",
                "config": row["config"],
                "market_title": row["market_title"],
                "cum_trades": float(row["cum_trades"]),
                "trade_progress": float(row["trade_progress"]),
                "yes_price": float(row["yes_price"]),
                "truth": float(row["truth"]),
                "tick": None,
                "ts": row["ts"],
                "volume": float(row["volume"]),
                "slug": row["slug"],
                "real_cum_trades": float(row["real_cum_trades"]) if "real_cum_trades" in row and pd.notna(row["real_cum_trades"]) else None,
            })
    return pd.DataFrame(sim_rows + real_rows)


def save_metric_table(rows: list[dict], name: str) -> None:
    cols = [
        "config", "market_key", "n_agents", "n_ticks", "truth_label",
        "signal_mu", "start_mid", "end_mid", "drift", "direction_score",
        "distance_to_truth", "volatility", "max_abs_step",
        "n_fills", "fills_per_agent_tick", "notional", "notional_per_agent",
        "active_trade_fill_rate", "cancel_per_fill",
        "price_response_per_1k_notional", "pnl_mean", "pnl_std", "pnl_spread",
    ]
    df = pd.DataFrame(rows)
    keep = [c for c in cols if c in df.columns]
    df[keep].round(4).to_csv(OUT_TBL / name, index=False)


# --- finalize_v15 -------------------------------------------------------------
def finalize_v15(
    fig,
    stem: str,
    source_data: pd.DataFrame | None = None,
    formats: tuple[str, ...] = FIG_FORMATS,
    pad: float = 0.4,
) -> dict:
    """Save figure + source CSV under docs/v15/figures/<fmt>/.

    ``stem`` is the filename stem without extension (e.g. ``4-1-4_宏观_消融价格图``).
    Each output format goes into ``figures/{png,svg,pdf,tiff}/<stem>.<ext>``;
    sibling source CSV (if given) lands at ``figures/data/<stem>.csv``.
    """
    apply_text_fonts(fig)
    fig.tight_layout(pad=pad)
    out: dict[str, str] = {}
    for fmt in formats:
        dpi = 600 if fmt == "tiff" else None
        target_dir = OUT_FIG / fmt
        target_dir.mkdir(parents=True, exist_ok=True)
        p = target_dir / f"{stem}.{fmt}"
        kw = {}
        if dpi is not None:
            kw["dpi"] = dpi
        fig.savefig(p, **kw)
        out[fmt] = str(p)
    if source_data is not None:
        data_dir = OUT_FIG / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        csv_path = data_dir / f"{stem}.csv"
        source_data.to_csv(csv_path, index=False)
        out["data"] = str(csv_path)
    plt.close(fig)
    return out


__all__ = [
    # constants
    "BLUE", "GREEN", "RED", "TEAL", "VIOLET", "GOLD",
    "NEUTRAL_LIGHT", "NEUTRAL_MID", "NEUTRAL_DARK",
    "BASE_MARKETS", "MARKET_LABEL", "MARKET_COLOR", "RQ1_MARKET_TITLE",
    "ACTION_ORDER", "ACTION_COLOR", "TRADING_ACTIONS", "ACTIVE_TRADE_ACTIONS",
    "ABLATION_MODULES",
    "FIG_FORMATS", "COL_DOUBLE_MM", "COL_SINGLE_MM",
    "ROOT", "V15", "OUT_BASE", "OUT_FIG", "OUT_TBL", "OUT_ANALYSIS",
    # helpers
    "config_name", "market_title_for", "safe_fig_name",
    "runs_of", "latest_runs_of", "grouped",
    "prior_for", "truth_yes", "outcome_label", "market_key_from_slug",
    "load_actions", "load_fills", "load_positions", "yes_mid_path", "metrics",
    "integer_xaxis", "result_label", "result_color",
    "path_rows", "try_real_trade_path", "real_path_for_plot",
    "split_terminal_settlement", "draw_market_cutoff", "real_path_source_rows",
    "simulated_trade_count_path", "cumulative_trade_map",
    "micro_trade_count_behavior_path", "real_trade_count_path",
    "real_actual_trade_count_path", "trade_count_source_data",
    "save_metric_table",
    "finalize_v15",
    "fig_size", "fig_size_vstack", "panel_label",
]
