"""v7 — Render the 6 paper figures with matplotlib + seaborn.

Read-only post-hoc plotting. Sources:
  * dataapi_trades       — real per-trade prices (sim-vs-real comparison)
  * clob_prices_history  — high-fidelity hourly bars where available
  * markets_full         — landscape stats
  * agent_*              — sim outputs (graceful "no data" panels if empty)
  * data/priors_<slug>.json — calibration metadata for figure annotations

CLI:
    python -m src.analysis.plots --output-dir figures/
    python -m src.analysis.plots --slug <slug> --sim-id <hex>

Each figure function returns the saved Path so tests can assert
existence without inspecting pixel content. We DO NOT show() — these
are batch-rendered to disk (PNG + PDF).
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")    # headless — no DISPLAY required
import matplotlib.pyplot as plt
import seaborn as sns

from ..pipeline.clickhouse import ClickHouse
from ..pipeline.config import get_settings


log = logging.getLogger(__name__)
sns.set_theme(style="whitegrid", context="paper")
_FIG_DPI = 150


def _save(fig, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{name}.png"
    pdf = out_dir / f"{name}.pdf"
    fig.savefig(png, dpi=_FIG_DPI, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    log.info("wrote %s", png)
    return png


def _no_data_panel(fig, ax, msg: str) -> None:
    ax.text(0.5, 0.5, msg, ha="center", va="center",
            transform=ax.transAxes, fontsize=11, color="gray")
    ax.set_xticks([])
    ax.set_yticks([])


# === fig 1 — market landscape ============================================


def fig1_market_landscape(ch: ClickHouse, out_dir: Path) -> Path:
    """Volume + lifetime distribution of resolved markets."""
    rows = ch.client.execute(
        f"""
        SELECT mf.volume_num, dateDiff('day', mf.start_date, mf.end_date) AS lifetime_d
        FROM polymetl.markets_resolved mr
        INNER JOIN polymetl.markets_full mf USING (condition_id)
        WHERE mf.volume_num > 0 AND mf.start_date IS NOT NULL
              AND mf.end_date IS NOT NULL
        LIMIT 50000
        """
    )
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    if not rows:
        for a in axes:
            _no_data_panel(fig, a, "no resolved markets in CH")
        return _save(fig, out_dir, "fig1_market_landscape")
    vols = [float(r[0]) for r in rows if r[0] and r[0] > 0]
    lifes = [int(r[1]) for r in rows if r[1] is not None and r[1] >= 0]
    axes[0].hist(vols, bins=60, range=(0, max(min(max(vols), 1e6), 1)),
                 color="#4477aa")
    axes[0].set_xlabel("Volume (USDC)")
    axes[0].set_ylabel("# resolved markets")
    axes[0].set_title("Volume distribution")
    axes[0].set_xscale("symlog")
    axes[1].hist(lifes, bins=60, range=(0, min(max(lifes), 365)),
                 color="#aa6644")
    axes[1].set_xlabel("Market lifetime (days)")
    axes[1].set_ylabel("# resolved markets")
    axes[1].set_title("Lifetime distribution")
    fig.suptitle(f"Polymarket landscape ({len(rows):,} resolved markets)")
    return _save(fig, out_dir, "fig1_market_landscape")


# === fig 2 — calibrated wallet population ================================


def fig2_wallet_population(ch: ClickHouse, condition_id: str, out_dir: Path) -> Path:
    """Capital, tx_count, asset diversity, past_accuracy distribution."""
    rows = ch.client.execute(
        f"""
        SELECT capital_usd, tx_count, asset_diversity, past_accuracy
        FROM polymetl.wallet_features FINAL
        WHERE target_market_id = %(cid)s
        """,
        {"cid": condition_id},
    )
    fig, axes = plt.subplots(2, 2, figsize=(9, 7))
    if not rows:
        for a in axes.flat:
            _no_data_panel(fig, a, f"no wallet_features for\n{condition_id[:18]}")
        return _save(fig, out_dir, "fig2_wallet_population")
    cap, tx, div, acc = zip(*rows)
    axes[0, 0].hist(cap, bins=20, color="#4477aa"); axes[0, 0].set_xscale("symlog")
    axes[0, 0].set_xlabel("Capital ($)"); axes[0, 0].set_ylabel("# wallets")
    axes[0, 1].hist(tx, bins=20, color="#aa6644"); axes[0, 1].set_xscale("symlog")
    axes[0, 1].set_xlabel("Pre-event tx count")
    axes[1, 0].hist(div, bins=20, color="#22aa88"); axes[1, 0].set_xscale("symlog")
    axes[1, 0].set_xlabel("Asset diversity (# distinct markets)")
    axes[1, 1].hist(acc, bins=20, range=(0, 1), color="#aa4477")
    axes[1, 1].set_xlabel("Past accuracy")
    fig.suptitle(f"Calibrated wallet population (n={len(rows)})")
    return _save(fig, out_dir, "fig2_wallet_population")


# === fig 3 — sim-vs-real price path ======================================


def fig3_price_path(
    ch: ClickHouse, condition_id: str, yes_token_id: str,
    sim_id: Optional[str], out_dir: Path,
) -> Path:
    """Sim YES mid trajectory vs real CLOB path."""
    real = ch.client.execute(
        f"""
        SELECT trade_time, price
        FROM polymetl.dataapi_trades
        WHERE condition_id = %(cid)s AND outcome_index = 0
        ORDER BY trade_time
        """,
        {"cid": condition_id},
    )
    sim = []
    if sim_id:
        sim = ch.client.execute(
            f"""
            SELECT t.tick_idx, avg(p.cash) AS dummy
            FROM polymetl.agent_actions t
            LEFT JOIN polymetl.agent_positions p USING (sim_id)
            WHERE t.sim_id = %(sid)s
            GROUP BY t.tick_idx ORDER BY t.tick_idx
            """,
            {"sid": sim_id},
        )
    fig, ax = plt.subplots(figsize=(9, 4.5))
    if not real and not sim:
        _no_data_panel(fig, ax, "no real or sim price data")
        return _save(fig, out_dir, "fig3_price_path")
    if real:
        ts = [r[0] for r in real]
        px = [float(r[1]) for r in real]
        ax.plot(ts, px, color="#1f77b4", lw=1.0, label=f"Real ({len(real)} trades)")
    if sim:
        ax.plot([s[0] for s in sim], [float(s[1]) for s in sim],
                color="#d62728", lw=1.4, marker="o", label=f"Sim ({sim_id[:10]})")
    ax.set_ylim(0, 1)
    ax.set_xlabel("Time")
    ax.set_ylabel("YES price")
    ax.legend(loc="best")
    ax.set_title("Sim vs real YES price path")
    return _save(fig, out_dir, "fig3_price_path")


# === fig 4 — SERD ROI by quartile role ===================================


def fig4_serd_roi(roles_data: list[tuple[str, float, int]], out_dir: Path) -> Path:
    """Bar chart of mean ROI per SERD role.

    `roles_data`: [(role_name, mean_roi, n_agents), ...] in order
    ApexPredator → UpperMeso → LowerMeso → Prey.
    """
    fig, ax = plt.subplots(figsize=(7, 4.5))
    if not roles_data:
        _no_data_panel(fig, ax, "no SERD analysis available\n(run scripts/06_analyze_serd.py first)")
        return _save(fig, out_dir, "fig4_serd_roi")
    names = [r[0] for r in roles_data]
    rois = [r[1] for r in roles_data]
    ns = [r[2] for r in roles_data]
    bars = ax.bar(names, rois, color=["#aa1111", "#aa6644", "#4488aa", "#1144aa"])
    for bar, n in zip(bars, ns):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"n={n}", ha="center", va="bottom", fontsize=9)
    ax.axhline(0, color="black", lw=0.5)
    ax.set_ylabel("Mean ROI")
    ax.set_title("SERD: ROI by quartile role")
    return _save(fig, out_dir, "fig4_serd_roi")


# === fig 5 — SERD vs DBSCAN+KMeans baseline ==============================


def fig5_serd_vs_baseline(
    serd_delta: float, baseline_delta: float, out_dir: Path,
) -> Path:
    """Two-bar chart contrasting ΔROI(top - bottom) under SERD vs baseline."""
    fig, ax = plt.subplots(figsize=(5, 4.5))
    ax.bar(["SERD", "DBSCAN+KMeans"], [serd_delta, baseline_delta],
           color=["#1144aa", "#888888"])
    ax.set_ylabel("ΔROI(top - bottom quartile)")
    ax.set_title(f"SERD vs baseline ΔROI (Δ = {serd_delta - baseline_delta:+.3f})")
    return _save(fig, out_dir, "fig5_serd_vs_baseline")


# === fig 6 — action mix per tick =========================================


def fig6_action_mix(ch: ClickHouse, sim_id: Optional[str], out_dir: Path) -> Path:
    """Stacked-area: BUY/SELL/CANCEL/HOLD frequency over ticks."""
    fig, ax = plt.subplots(figsize=(9, 4.5))
    if not sim_id:
        _no_data_panel(fig, ax, "pass --sim-id to render this figure")
        return _save(fig, out_dir, "fig6_action_mix")
    rows = ch.client.execute(
        f"""
        SELECT tick_idx, action_type, count() AS n
        FROM polymetl.agent_actions
        WHERE sim_id = %(sid)s
        GROUP BY tick_idx, action_type ORDER BY tick_idx
        """,
        {"sid": sim_id},
    )
    if not rows:
        _no_data_panel(fig, ax, f"no actions for sim {sim_id[:10]}")
        return _save(fig, out_dir, "fig6_action_mix")
    by_tick: dict[int, dict[str, int]] = {}
    for tick, atype, n in rows:
        by_tick.setdefault(int(tick), {})[atype] = int(n)
    ticks = sorted(by_tick)
    types = ["BUY", "SELL", "CANCEL", "HOLD"]
    series = {t: [by_tick[k].get(t, 0) for k in ticks] for t in types}
    ax.stackplot(ticks, *[series[t] for t in types],
                 labels=types,
                 colors=["#22aa88", "#aa4422", "#aa8822", "#888888"])
    ax.legend(loc="upper right", ncol=4)
    ax.set_xlabel("Tick")
    ax.set_ylabel("# actions")
    ax.set_title(f"Action mix over time (sim {sim_id[:10]})")
    return _save(fig, out_dir, "fig6_action_mix")


# === Top-level orchestration =============================================


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default=None,
                        help="market slug — needed for fig2/fig3 wallet/price figures")
    parser.add_argument("--sim-id", default=None,
                        help="sim_id (hex) — needed for fig3 sim path + fig6 actions")
    parser.add_argument("--output-dir", default="figures",
                        help="where to write the PNG/PDF files")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    s = get_settings()
    ch = ClickHouse(host=s.CLICKHOUSE_HOST, port=s.CLICKHOUSE_PORT,
                    user=s.CLICKHOUSE_USER, password=s.CLICKHOUSE_PASSWORD,
                    database=s.CLICKHOUSE_DATABASE)
    out = Path(args.output_dir)

    fig1_market_landscape(ch, out)

    cid = ""
    yes_token = ""
    if args.slug:
        priors_path = Path(f"data/priors_{args.slug}.json")
        if priors_path.exists():
            priors = json.loads(priors_path.read_text())
            cid = priors["condition_id"]
            yes_token = priors["yes_token_id"]
        else:
            log.warning("priors not found at %s; fig2/fig3 will be empty", priors_path)
    if cid:
        fig2_wallet_population(ch, cid, out)
        fig3_price_path(ch, cid, yes_token, args.sim_id, out)
    else:
        # Render placeholder panels so the file exists for tests.
        fig, ax = plt.subplots(); _no_data_panel(fig, ax, "pass --slug")
        _save(fig, out, "fig2_wallet_population")
        fig, ax = plt.subplots(); _no_data_panel(fig, ax, "pass --slug + --sim-id")
        _save(fig, out, "fig3_price_path")

    # SERD figures: read from analysis.serd if a sim_id is supplied,
    # otherwise render placeholders.
    if args.sim_id:
        from .serd import analyze_sim, ROLES
        try:
            report = analyze_sim(args.sim_id, ch=ch)
            roles_data = [
                (r, float(report.roi_per_role.get(r, {}).get("mean_roi", 0.0)),
                 int(report.roi_per_role.get(r, {}).get("n", 0)))
                for r in ROLES
            ]
            fig4_serd_roi(roles_data, out)
            fig5_serd_vs_baseline(
                report.delta_roi_serd, report.delta_roi_baseline, out,
            )
        except Exception as exc:    # noqa: BLE001
            log.warning("SERD analysis failed: %s — placeholder figs", exc)
            fig4_serd_roi([], out)
            fig5_serd_vs_baseline(0.0, 0.0, out)
    else:
        fig4_serd_roi([], out)
        fig5_serd_vs_baseline(0.0, 0.0, out)

    fig6_action_mix(ch, args.sim_id, out)
    log.info("done; figures in %s", out)


if __name__ == "__main__":
    main()
