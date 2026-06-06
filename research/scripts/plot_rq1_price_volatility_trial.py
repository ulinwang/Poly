"""Trial RQ1 figure: real vs simulated YES price volatility paths.

This is a standalone draft figure for thesis discussion. It does not alter the
main thesis rendering pipeline.

Run:
    uv run python scripts/plot_rq1_price_volatility_trial.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _thesis_style import (
    BLUE,
    BLUE_LIGHT,
    COL_DOUBLE_MM,
    GREEN_DEEP,
    NEUTRAL_DARK,
    NEUTRAL_LIGHT,
    NEUTRAL_MID,
    RED,
    apply_style,
    fig_size,
    finalize,
)
from data.query._ch import get_ch
from data.query.markets import get_market_meta


apply_style(font_size=7.2)

ROOT = Path(__file__).resolve().parent.parent
V14 = ROOT / "output" / "v14" / "rq1"
OUT_FIG = ROOT / "docs" / "v14" / "figures"
FIG_NAME = "试稿_真实与模拟市场价格波动对照"


MARKETS = [
    {
        "slug": "will-trump-deploy-national-guard-in-dc-by-monday",
        "label": "Trump 国民警卫队",
        "note": "真值 YES；模拟背离",
    },
    {
        "slug": "btc-above-100k-till-2025-end",
        "label": "BTC 年底前跌破 100k",
        "note": "真值 YES；轻微靠近",
    },
    {
        "slug": "will-bitcoin-reach-125k-in-july-846-114",
        "label": "Bitcoin 7 月达 125k",
        "note": "真值 NO；轻微靠近",
    },
    {
        "slug": "will-the-supreme-court-rule-in-favor-of-trumps-tariffs",
        "label": "最高法院关税案",
        "note": "真值 NO；模拟背离",
    },
]


def truth_yes(slug: str) -> float:
    p = ROOT / f"data/priors_{slug}.json"
    d = json.loads(p.read_text())
    return 1.0 if int(d["winning_idx"]) == 0 else 0.0


def real_yes_prices(slug: str) -> pd.DataFrame:
    meta = get_market_meta(slug)
    if not meta:
        raise RuntimeError(f"Missing market metadata for {slug}")
    rows = get_ch().client.execute(
        """
        SELECT trade_time, price
        FROM polymetl.dataapi_trades
        WHERE condition_id = %(cid)s
          AND outcome_index = 0
        ORDER BY trade_time
        """,
        {"cid": meta["condition_id"]},
    )
    df = pd.DataFrame(rows, columns=["time", "yes_price"])
    if df.empty:
        return df.assign(progress=[])
    ts = pd.to_datetime(df["time"])
    denom = max((ts.max() - ts.min()).total_seconds(), 1.0)
    df["progress"] = (ts - ts.min()).dt.total_seconds() / denom
    df["source"] = "real"
    return df


def simulated_yes_paths(slug: str) -> pd.DataFrame:
    rows = []
    for run in sorted(V14.glob("2026*/")):
        meta_path = run / "meta.json"
        actions_path = run / "raw" / "agent_actions.parquet"
        if not meta_path.exists() or not actions_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta["config"]["market"]["slug"] != slug:
            continue
        actions = pd.read_parquet(actions_path)
        mids = (
            actions.dropna(subset=["yes_mid_after"])
            .groupby("tick_idx")["yes_mid_after"]
            .last()
            .reset_index()
            .sort_values("tick_idx")
        )
        if mids.empty:
            continue
        max_tick = max(float(mids["tick_idx"].max()), 1.0)
        seed = meta["config"].get("run", {}).get("seed")
        if seed is None:
            seed = run.name.split("_s")[-1].split("-")[0]
        for _, row in mids.iterrows():
            rows.append(
                {
                    "source": "simulation",
                    "seed": str(seed),
                    "tick_idx": int(row["tick_idx"]),
                    "progress": float(row["tick_idx"]) / max_tick,
                    "yes_price": float(row["yes_mid_after"]),
                }
            )
    return pd.DataFrame(rows)


def binned_real_path(df: pd.DataFrame, bins: int = 80) -> pd.DataFrame:
    if df.empty:
        return df
    cuts = pd.cut(df["progress"], bins=np.linspace(0, 1, bins + 1), include_lowest=True)
    out = (
        df.groupby(cuts, observed=True)
        .agg(progress=("progress", "mean"), yes_price=("yes_price", "median"))
        .dropna()
        .reset_index(drop=True)
    )
    return out


def add_reference_lines(ax, truth: float) -> None:
    target_color = GREEN_DEEP if truth == 1.0 else RED
    ax.axhline(1.0, color=GREEN_DEEP, lw=0.6, ls=":", alpha=0.65)
    ax.axhline(0.5, color=NEUTRAL_MID, lw=0.6, ls="--", alpha=0.55)
    ax.axhline(0.0, color=RED, lw=0.6, ls=":", alpha=0.65)
    ax.axhline(truth, color=target_color, lw=1.0, ls="-", alpha=0.22)
    ax.set_ylim(-0.04, 1.04)
    ax.set_xlim(-0.02, 1.02)


def main() -> None:
    fig, axes = plt.subplots(
        len(MARKETS),
        2,
        figsize=fig_size(COL_DOUBLE_MM, 168),
        sharex="col",
        sharey=True,
    )
    source_rows = []

    for row_idx, spec in enumerate(MARKETS):
        slug = spec["slug"]
        truth = truth_yes(slug)
        target_text = "趋近 1.00" if truth == 1.0 else "趋近 0.00"

        real = real_yes_prices(slug)
        sim = simulated_yes_paths(slug)
        smooth = binned_real_path(real)

        ax_real = axes[row_idx, 0]
        ax_sim = axes[row_idx, 1]

        add_reference_lines(ax_real, truth)
        add_reference_lines(ax_sim, truth)

        if not real.empty:
            ax_real.scatter(
                real["progress"],
                real["yes_price"],
                s=2,
                color=NEUTRAL_LIGHT,
                alpha=0.35,
                edgecolors="none",
            )
            ax_real.plot(
                smooth["progress"],
                smooth["yes_price"],
                color=NEUTRAL_DARK,
                lw=1.15,
                label="真实成交价中位路径",
            )
            for r in real.itertuples(index=False):
                source_rows.append(
                    {
                        "slug": slug,
                        "panel": "real",
                        "series": "raw_trade",
                        "progress": float(r.progress),
                        "yes_price": float(r.yes_price),
                        "truth": truth,
                    }
                )

        if not sim.empty:
            for seed, sub in sim.groupby("seed"):
                ax_sim.plot(
                    sub["progress"],
                    sub["yes_price"],
                    color=BLUE_LIGHT,
                    lw=0.75,
                    alpha=0.55,
                )
            mean = (
                sim.groupby("progress")["yes_price"]
                .mean()
                .reset_index()
                .sort_values("progress")
            )
            ax_sim.plot(
                mean["progress"],
                mean["yes_price"],
                color=BLUE,
                lw=1.35,
                label="三次仿真均值",
            )
            for r in sim.itertuples(index=False):
                source_rows.append(
                    {
                        "slug": slug,
                        "panel": "simulation",
                        "series": f"seed_{r.seed}",
                        "progress": float(r.progress),
                        "yes_price": float(r.yes_price),
                        "truth": truth,
                    }
                )

        ax_real.set_ylabel("YES 价格")
        ax_real.text(
            0.01,
            0.92,
            f"{spec['label']}\n{spec['note']}；正确方向：{target_text}",
            transform=ax_real.transAxes,
            ha="left",
            va="top",
            fontsize=6.2,
            color=NEUTRAL_DARK,
        )
        ax_sim.text(
            0.01,
            0.92,
            f"正确方向：{target_text}",
            transform=ax_sim.transAxes,
            ha="left",
            va="top",
            fontsize=6.2,
            color=NEUTRAL_DARK,
        )

        if row_idx == 0:
            ax_real.set_title("真实市场价格波动", color=NEUTRAL_DARK)
            ax_sim.set_title("模拟市场价格波动", color=NEUTRAL_DARK)
            ax_real.legend(loc="lower right", fontsize=6.0)
            ax_sim.plot([], [], color=BLUE_LIGHT, lw=0.75, alpha=0.55,
                        label="单次仿真")
            ax_sim.plot([], [], color=NEUTRAL_MID, lw=0.6, ls="--",
                        label="0.50 分界线")
            ax_sim.legend(loc="lower right", fontsize=6.0)

    for ax in axes[-1, :]:
        ax.set_xlabel("归一化进度")

    finalize(
        fig,
        OUT_FIG / FIG_NAME,
        source_data=pd.DataFrame(source_rows),
        formats=("png", "svg", "pdf"),
        pad=0.25,
    )
    print(OUT_FIG / f"{FIG_NAME}.png")
    print(OUT_FIG / "data" / f"{FIG_NAME}.csv")


if __name__ == "__main__":
    main()
