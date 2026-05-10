"""v7 — Render paper tables in markdown + LaTeX.

Reads from ClickHouse (sim outputs + wallet_features) plus the
priors JSON. Each `render_*` function returns a (markdown, latex)
tuple; `main()` writes them to `tables/`.

CLI:
    python -m src.thesis.tables --slug <slug> --sim-id <hex>
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
from pathlib import Path
from typing import Optional

from ..pipeline.clickhouse import ClickHouse
from ..pipeline.config import get_settings


log = logging.getLogger(__name__)


# === Markdown / LaTeX helpers ============================================


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    lines = ["| " + " | ".join(headers) + " |", sep]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines) + "\n"


def _latex_table(
    headers: list[str], rows: list[list[str]], caption: str, label: str,
) -> str:
    cols = "l" + "r" * (len(headers) - 1)
    lines = [
        r"\begin{table}[ht]", r"\centering",
        rf"\caption{{{caption}}}", rf"\label{{{label}}}",
        rf"\begin{{tabular}}{{{cols}}}", r"\toprule",
        " & ".join(headers) + r" \\", r"\midrule",
    ]
    for r in rows:
        lines.append(" & ".join(r) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines) + "\n"


def _write_pair(out_dir: Path, name: str, md: str, latex: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.md").write_text(md)
    (out_dir / f"{name}.tex").write_text(latex)
    log.info("wrote %s.{md,tex}", out_dir / name)


# === tab1 — wallet population summary ====================================


def render_wallet_population(
    ch: ClickHouse, condition_id: str,
) -> tuple[str, str]:
    rows = ch.client.execute(
        f"""
        SELECT capital_usd, tx_count, asset_diversity, past_accuracy,
               n_resolved_prior
        FROM polymetl.wallet_features FINAL
        WHERE target_market_id = %(cid)s
        """,
        {"cid": condition_id},
    )
    headers = ["Statistic", "Capital ($)", "TX count", "Asset diversity",
               "Past accuracy", "N resolved prior"]
    if not rows:
        body = [["(no rows)", "-", "-", "-", "-", "-"]]
    else:
        cols = list(zip(*rows))
        def _stats(vals: list[float]) -> list[str]:
            f = [float(v) for v in vals]
            return [
                f"{min(f):.2f}", f"{statistics.median(f):.2f}",
                f"{statistics.fmean(f):.2f}", f"{max(f):.2f}",
            ]
        body = []
        for stat_i, label in enumerate(["min", "median", "mean", "max"]):
            row = [label]
            for col in cols:
                row.append(_stats(col)[stat_i])
            body.append(row)
        body.append([f"n = {len(rows)}", "", "", "", "", ""])
    md = _md_table(headers, body)
    latex = _latex_table(
        headers, body,
        caption="Calibrated wallet population summary statistics",
        label="tab:wallet_population",
    )
    return md, latex


# === tab2 — SERD roles ===================================================


def render_serd_roles(
    ch: ClickHouse, sim_id: str,
) -> tuple[str, str]:
    rows = ch.client.execute(
        f"""
        SELECT role, n_agents, mean_roi, vol_share
        FROM polymetl.serd_results FINAL
        WHERE sim_id = %(sid)s AND method = 'SERD'
        ORDER BY mean_roi DESC
        """,
        {"sid": sim_id},
    )
    headers = ["Role", "N agents", "Mean ROI", "Volume share"]
    body = (
        [[r[0], str(int(r[1])), f"{float(r[2]):+.4f}", f"{float(r[3]):.3f}"]
         for r in rows]
        if rows else [["(no SERD results yet)", "-", "-", "-"]]
    )
    md = _md_table(headers, body)
    latex = _latex_table(
        headers, body,
        caption="SERD quartile roles: ROI and volume share",
        label="tab:serd_roles",
    )
    return md, latex


# === tab3 — SERD vs DBSCAN+KMeans ========================================


def render_vs_baseline(ch: ClickHouse, sim_id: str) -> tuple[str, str]:
    rows = ch.client.execute(
        f"""
        SELECT method, role, n_agents, mean_roi
        FROM polymetl.serd_results FINAL
        WHERE sim_id = %(sid)s
        ORDER BY method, mean_roi DESC
        """,
        {"sid": sim_id},
    )
    headers = ["Method", "Role", "N agents", "Mean ROI"]
    body = (
        [[r[0], r[1], str(int(r[2])), f"{float(r[3]):+.4f}"] for r in rows]
        if rows else [["(no results yet)", "-", "-", "-"]]
    )
    md = _md_table(headers, body)
    latex = _latex_table(
        headers, body,
        caption="SERD vs DBSCAN+KMeans baseline: ROI separation",
        label="tab:vs_baseline",
    )
    return md, latex


# === tab4 — priors summary ===============================================


def render_priors_summary(slug: str, data_dir: Path) -> tuple[str, str]:
    path = data_dir / f"priors_{slug}.json"
    if not path.exists():
        body = [[f"(priors_{slug}.json not found)", "-", "-"]]
    else:
        priors = json.loads(path.read_text())
        b = priors.get("bootstrap", {})
        sm = priors.get("signal_mu_meta", {})
        body = [
            ["market_open_iso", priors.get("market_open_iso", "-"), "dataapi_trades.min(trade_time)"],
            ["tick_size", str(priors.get("tick_size", "-")), "clob_markets.minimum_tick_size"],
            ["taker_fee_bps", f"{priors.get('taker_fee_bps', 0.0):.4f}", "clob_markets.taker_base_fee"],
            ["n_ticks", str(priors.get("n_ticks", "-")), "lifetime/6h, clamped [8,48]"],
            ["signal_mu", f"{priors.get('signal_mu', 0.0):.4f}", f"{sm.get('source', '-')} (n={sm.get('n_obs', 0)})"],
            ["bootstrap.anchor_yes", f"{b.get('anchor_yes', 0.0):.4f}", b.get("source", "-")],
            ["bootstrap.spread", f"{b.get('spread', 0.0):.4f}", b.get("source", "-")],
            ["bootstrap.depth_per_level", f"{b.get('depth_per_level', 0.0):.0f}", b.get("source", "-")],
            ["bootstrap.depth_levels", str(b.get("depth_levels", "-")), "constant (3, see EMPIRICAL_PRIORS.md)"],
            ["winning_idx", str(priors.get("winning_idx", -1)), "markets_resolved"],
        ]
    headers = ["Prior", "Value", "Source"]
    md = _md_table(headers, body)
    latex = _latex_table(
        headers, body,
        caption=f"Empirical priors for slug {slug}",
        label="tab:priors_summary",
    )
    return md, latex


# === Top-level orchestration =============================================


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--sim-id", default=None)
    parser.add_argument("--output-dir", default="tables")
    parser.add_argument("--data-dir", default="data")
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

    # tab1 needs condition_id from priors
    priors_path = Path(args.data_dir) / f"priors_{args.slug}.json"
    if not priors_path.exists():
        raise SystemExit(
            f"missing {priors_path}; run scripts/03_derive_calibration_priors.py first"
        )
    priors = json.loads(priors_path.read_text())
    cid = priors["condition_id"]

    md, tex = render_wallet_population(ch, cid)
    _write_pair(out, "tab1_wallet_population", md, tex)
    md, tex = render_priors_summary(args.slug, Path(args.data_dir))
    _write_pair(out, "tab4_priors_summary", md, tex)

    if args.sim_id:
        md, tex = render_serd_roles(ch, args.sim_id)
        _write_pair(out, "tab2_serd_roles", md, tex)
        md, tex = render_vs_baseline(ch, args.sim_id)
        _write_pair(out, "tab3_vs_baseline", md, tex)
    else:
        log.info("no --sim-id; skipping tab2/tab3 (need a completed sim)")


if __name__ == "__main__":
    main()
