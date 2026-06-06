"""v10 — side-by-side comparison of multiple experiments.

Reads N exp_dirs from disk, builds a comparison report:
  - YES mid trajectory (overlaid line chart)
  - PnL distribution (overlapping histograms)
  - Action mix (grouped bar)
  - Headline statistics table (md + json)

Usage:
    python -m experiments.compare \\
        --label baseline=output_concurrent/20260511T095017-... \\
        --label archetype-n9=output/<exp_id> \\
        --label archetype-n30=output/<exp_id> \\
        --label no-signal=output/<exp_id> \\
        --out-dir comparison/
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

COLORS = {
    "baseline":      "#1f77b4",
    "archetype-n9":  "#2ca02c",
    "archetype-n30": "#9467bd",
    "no-signal":     "#d62728",
}


def _load_exp(exp_dir: Path) -> dict:
    meta = json.loads((exp_dir / "meta.json").read_text())
    summary = (
        json.loads((exp_dir / "analysis" / "summary.json").read_text())
        if (exp_dir / "analysis" / "summary.json").exists() else {}
    )
    actions = pd.read_parquet(exp_dir / "raw" / "agent_actions.parquet")
    positions = pd.read_parquet(exp_dir / "raw" / "agent_positions.parquet")
    personas = pd.read_parquet(exp_dir / "raw" / "agent_personas.parquet")
    return dict(meta=meta, summary=summary, actions=actions,
                positions=positions, personas=personas, dir=exp_dir)


def plot_yes_mid(experiments: dict[str, dict], out: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    for label, exp in experiments.items():
        a = exp["actions"]
        by_tick = a.groupby("tick_idx")["yes_mid_after"].last().sort_index()
        ax.plot(by_tick.index, by_tick.values, marker="o", lw=1.6,
                label=label, color=COLORS.get(label, None), alpha=0.85)
    ax.axhline(0.0, color="grey", lw=0.5, ls="--", label="resolved NO = 0")
    ax.axhline(0.5, color="grey", lw=0.3)
    ax.set_xlabel("tick")
    ax.set_ylabel("YES mid")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("YES mid trajectory across experiments")
    ax.legend(loc="best", fontsize=9)
    p = out / "compare_yes_mid.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    fig.savefig(p.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    return p


def _final_pnl(exp: dict, winning_idx: int) -> pd.Series:
    positions = exp["positions"]
    personas = exp["personas"]
    final = positions[positions["tick_idx"] == positions["tick_idx"].max()].copy()
    cap = dict(zip(personas["agent_id"], personas["capital_initial"]))
    final["capital"] = final["agent_id"].map(cap)
    yes_payoff = 1.0 if winning_idx == 0 else 0.0
    no_payoff = 1.0 - yes_payoff
    final["pnl"] = (
        final["cash"] + final["yes_shares"] * yes_payoff
        + final["no_shares"] * no_payoff - final["capital"]
    )
    return final["pnl"]


def plot_pnl_dist(experiments: dict[str, dict], winning_idx: int,
                   out: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    bins = np.linspace(-2000, 2000, 25)
    for label, exp in experiments.items():
        pnl = _final_pnl(exp, winning_idx)
        ax.hist(pnl, bins=bins, alpha=0.5, label=f"{label} (n={len(pnl)})",
                color=COLORS.get(label, None))
    ax.axvline(0, color="black", lw=0.5)
    ax.set_xlabel("PnL ($)")
    ax.set_ylabel("# agents")
    ax.set_title("Per-agent PnL distribution across experiments")
    ax.legend(loc="best", fontsize=9)
    p = out / "compare_pnl_dist.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    fig.savefig(p.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    return p


def plot_action_mix(experiments: dict[str, dict], out: Path) -> Path:
    types = ["LIMIT", "MARKET", "CANCEL", "SPLIT", "MERGE", "HOLD"]
    width = 0.8 / len(experiments)
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    x = np.arange(len(types))
    for i, (label, exp) in enumerate(experiments.items()):
        a = exp["actions"]
        counts = a["action_type"].value_counts()
        pcts = [counts.get(t, 0) / len(a) * 100 for t in types]
        ax.bar(x + i * width, pcts, width, label=label,
               color=COLORS.get(label, None))
    ax.set_xticks(x + width * (len(experiments) - 1) / 2)
    ax.set_xticklabels(types)
    ax.set_ylabel("% of total actions")
    ax.set_title("Action-type mix across experiments")
    ax.legend(loc="best", fontsize=9)
    p = out / "compare_action_mix.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    fig.savefig(p.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    return p


def summary_table(experiments: dict[str, dict],
                  winning_idx: int) -> tuple[str, dict]:
    """Build a side-by-side stats table; returns (markdown, dict)."""
    rows = []
    for label, exp in experiments.items():
        meta = exp["meta"]
        a = exp["actions"]
        pnl = _final_pnl(exp, winning_idx)
        last_mid = a.groupby("tick_idx")["yes_mid_after"].last().iloc[-1]
        d = {
            "experiment": label,
            "n_agents": meta["n_agents"],
            "n_ticks": meta["n_ticks"],
            "yes_mid_final": round(float(last_mid), 3),
            "direction_correct": bool((last_mid < 0.5) == (winning_idx == 1)),
            "pnl_mean": float(pnl.mean()),
            "pnl_std": float(pnl.std(ddof=0)),
            "pnl_min": float(pnl.min()),
            "pnl_max": float(pnl.max()),
            "cancel_pct": float(
                (a["action_type"] == "CANCEL").sum() / len(a) * 100,
            ),
            "limit_pct": float(
                (a["action_type"] == "LIMIT").sum() / len(a) * 100,
            ),
            "n_actions": len(a),
        }
        rows.append(d)

    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        cells = []
        for h in headers:
            v = r[h]
            if isinstance(v, float):
                cells.append(f"{v:.2f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines), {"rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", action="append", required=True,
                        help="name=path/to/exp_dir; pass multiple times")
    parser.add_argument("--winning-idx", type=int, default=1,
                        help="resolution index (0=YES wins, 1=NO wins)")
    parser.add_argument("--out-dir", default="comparison/")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    experiments = {}
    for spec in args.label:
        if "=" not in spec:
            raise SystemExit(f"--label spec must be name=path, got {spec!r}")
        name, path = spec.split("=", 1)
        exp = _load_exp(Path(path))
        experiments[name.strip()] = exp
        log.info("loaded %s ← %s (sim_id=%s)", name, path, exp["meta"]["sim_id"][:10])

    p1 = plot_yes_mid(experiments, out);   log.info("wrote %s", p1)
    p2 = plot_pnl_dist(experiments, args.winning_idx, out); log.info("wrote %s", p2)
    p3 = plot_action_mix(experiments, out); log.info("wrote %s", p3)

    md, summary = summary_table(experiments, args.winning_idx)
    (out / "comparison_summary.md").write_text(md + "\n")
    (out / "comparison_summary.json").write_text(json.dumps(summary, indent=2))
    print("\n=== Side-by-side summary ===\n")
    print(md)


if __name__ == "__main__":
    main()
