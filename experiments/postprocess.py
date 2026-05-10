"""After-the-sim writers: analysis/ + figure/ subtrees.

Called by `experiments.runner.run_experiment` AFTER `env.settle()`
(both in live mode AND in --dry-run, since most of these can be
computed from the raw parquet alone).

Output paths inside `out_dir = output/<exp_id>/`:
    analysis/role_assignments.parquet     SERD per-agent labels
    analysis/pnl_by_persona.parquet       per-persona PnL summary
    analysis/summary.json                 headline metrics
    analysis/tables/{tab1..tab4}.{md,tex} markdown + LaTeX
    figure/0N_<name>.{png,pdf}            6 figures
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from experiments.analysis import pnl as pnl_mod, serd, tables
from experiments.parquet_sink import write_parquet

log = logging.getLogger(__name__)


def _write_role_assignments(
    sim_id: str, role_of: dict, roi_role: dict, out_dir: Path,
    compression: str = "zstd",
) -> int:
    rows = []
    for aid, role in role_of.items():
        rows.append((sim_id, aid, role,
                     float(roi_role.get(role, {}).get("mean_roi", 0.0))))
    return write_parquet(
        rows, ["sim_id", "agent_id", "role", "role_mean_roi"],
        out_dir / "analysis" / "role_assignments.parquet", compression,
    )


def _write_pnl_by_persona(
    sim_id: str, pnl: dict[int, float], persona_of: dict[int, str],
    out_dir: Path, compression: str = "zstd",
) -> int:
    by_p = pnl_mod.aggregate_by_persona(pnl, persona_of)
    rows = []
    for ptype, stats in by_p.items():
        rows.append((sim_id, ptype, stats["n"], stats["mean"],
                     stats["median"], stats["min"], stats["max"]))
    return write_parquet(
        rows, ["sim_id", "persona_type", "n", "mean", "median", "min", "max"],
        out_dir / "analysis" / "pnl_by_persona.parquet", compression,
    )


def _write_tables(
    out_dir: Path, slug: str, sim_id: Optional[str], data_dir: Path,
    ch=None,
) -> dict[str, Path]:
    """Render the 4 paper tables into analysis/tables/."""
    tdir = out_dir / "analysis" / "tables"
    tdir.mkdir(parents=True, exist_ok=True)

    # tab4 needs only priors JSON — always renders.
    md, tex = tables.render_priors_summary(slug, data_dir)
    (tdir / "tab4_priors_summary.md").write_text(md)
    (tdir / "tab4_priors_summary.tex").write_text(tex)

    if ch is None:
        log.warning("no CH; skipping tab1/tab2/tab3 (need wallet_features + serd_results)")
        return {"tab4": tdir / "tab4_priors_summary.md"}

    from data.query._ch import get_ch
    ch_eff = get_ch(ch)
    priors = json.loads((data_dir / f"priors_{slug}.json").read_text())
    cid = priors["condition_id"]

    md, tex = tables.render_wallet_population(ch_eff, cid)
    (tdir / "tab1_wallet_population.md").write_text(md)
    (tdir / "tab1_wallet_population.tex").write_text(tex)

    if sim_id:
        md, tex = tables.render_serd_roles(ch_eff, sim_id)
        (tdir / "tab2_serd_roles.md").write_text(md)
        (tdir / "tab2_serd_roles.tex").write_text(tex)
        md, tex = tables.render_vs_baseline(ch_eff, sim_id)
        (tdir / "tab3_vs_baseline.md").write_text(md)
        (tdir / "tab3_vs_baseline.tex").write_text(tex)
    return {p.stem: p for p in tdir.glob("*.md")}


def _write_figures(
    out_dir: Path, slug: str, sim_id: Optional[str],
    data_dir: Path, ch=None,
    role_summary: list[tuple[str, float, int]] | None = None,
    delta_serd: float = 0.0, delta_baseline: float = 0.0,
) -> list[Path]:
    """Render 6 figures into figure/ with NN_<name>.{png,pdf}."""
    from experiments.plots import _shared as plots

    fdir = out_dir / "figure"
    fdir.mkdir(parents=True, exist_ok=True)

    cid = ""
    yes_token = ""
    priors_path = data_dir / f"priors_{slug}.json"
    if priors_path.exists():
        priors = json.loads(priors_path.read_text())
        cid = priors["condition_id"]
        yes_token = priors["yes_token_id"]

    paths: list[Path] = []

    # Each figure module renders into its own filename. Wrap every
    # call so a single broken plot doesn't kill the others.
    def _try(name: str, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:        # noqa: BLE001
            log.warning("plot %s failed: %s — skipping", name, exc)
            return None

    if ch is not None:
        from data.query._ch import get_ch
        ch_eff = get_ch(ch)
        p = _try("fig1", plots.fig1_market_landscape, ch_eff, fdir)
        if p: paths.append(p)
        if cid:
            p = _try("fig2", plots.fig2_wallet_population, ch_eff, cid, fdir)
            if p: paths.append(p)
            p = _try("fig3", plots.fig3_price_path,
                      ch_eff, cid, yes_token, sim_id, fdir)
            if p: paths.append(p)
        p = _try("fig6", plots.fig6_action_mix, ch_eff, sim_id, fdir)
        if p: paths.append(p)
    p = _try("fig4", plots.fig4_serd_roi, role_summary or [], fdir)
    if p: paths.append(p)
    p = _try("fig5", plots.fig5_serd_vs_baseline,
              delta_serd, delta_baseline, fdir)
    if p: paths.append(p)

    # Rename to the v8 convention 0N_<name>.{png,pdf} with stable mapping.
    rename_map = {
        "fig1_market_landscape":  "01_market_landscape",
        "fig2_wallet_population": "02_wallet_population",
        "fig3_price_path":        "03_price_curve",
        "fig4_serd_roi":          "04_role_quartiles",
        "fig5_serd_vs_baseline":  "05_pnl_distribution",
        "fig6_action_mix":        "06_action_mix",
    }
    final: list[Path] = []
    for p in paths:
        new_stem = rename_map.get(p.stem, p.stem)
        for ext in (".png", ".pdf"):
            src = p.with_suffix(ext)
            if src.exists():
                dst = src.with_name(f"{new_stem}{ext}")
                src.replace(dst)
                final.append(dst)
    return final


def write_summary_json(
    out_dir: Path, sim_id: str, n_agents: int, n_ticks: int,
    pnl: dict[int, float], priors_summary: dict,
    serd_report=None,
) -> None:
    """Headline metrics consumed by docs / dashboards."""
    out = {
        "sim_id": sim_id,
        "n_agents": n_agents, "n_ticks": n_ticks,
        "pnl_mean": (sum(pnl.values()) / len(pnl)) if pnl else 0.0,
        "pnl_min": min(pnl.values()) if pnl else 0.0,
        "pnl_max": max(pnl.values()) if pnl else 0.0,
        "priors": priors_summary,
    }
    if serd_report is not None:
        out["serd"] = {
            "n_agents": serd_report.n_agents,
            "delta_roi_serd": serd_report.delta_roi_serd,
            "delta_roi_baseline": serd_report.delta_roi_baseline,
            "monotonic": serd_report.monotonic,
            "roi_per_role": {
                role: dict(d) for role, d in serd_report.roi_per_role.items()
            },
        }
    (out_dir / "analysis").mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis" / "summary.json").write_text(
        json.dumps(out, indent=2, default=str),
    )


def run_postprocess(
    *,
    out_dir: Path, slug: str, sim, pnl: dict[int, float],
    priors_summary: dict, data_dir: Path = Path("data"),
    compression: str = "zstd", ch=None, want_serd: bool = True,
) -> dict:
    """Full post-sim flow: analysis/* + figure/* + summary.json.

    `sim` is the env.state Simulation. `ch` is the ClickHouse client
    (or None to skip queries that need real DB access)."""
    persona_of = {a.agent_id: a.persona.persona_type for a in sim.agents}
    out_dir.mkdir(parents=True, exist_ok=True)

    # SERD analysis (writes to analysis/role_assignments.parquet)
    serd_report = None
    role_summary: list[tuple[str, float, int]] = []
    delta_serd = 0.0
    delta_baseline = 0.0
    if want_serd and ch is not None and sim.fills_log:
        try:
            serd_report = serd.analyze_sim(sim.sim_id, ch=ch)
            _write_role_assignments(
                sim.sim_id, serd_report.role_of, serd_report.roi_per_role,
                out_dir, compression,
            )
            role_summary = [
                (r, float(serd_report.roi_per_role.get(r, {}).get("mean_roi", 0.0)),
                 int(serd_report.roi_per_role.get(r, {}).get("n", 0)))
                for r in serd.ROLES
            ]
            delta_serd = serd_report.delta_roi_serd
            delta_baseline = serd_report.delta_roi_baseline
        except Exception as exc:           # noqa: BLE001
            log.warning("SERD analysis failed: %s — skipping", exc)

    # PnL by persona
    _write_pnl_by_persona(sim.sim_id, pnl, persona_of, out_dir, compression)

    # Tables (md + tex). tab2/tab3 need serd_results — pass sim_id only
    # when SERD actually ran.
    table_sim_id = sim.sim_id if serd_report is not None else None
    try:
        _write_tables(out_dir, slug, table_sim_id, data_dir, ch=ch)
    except Exception as exc:        # noqa: BLE001
        log.warning("tables render failed: %s", exc)

    # Figures
    try:
        _write_figures(out_dir, slug, sim.sim_id, data_dir, ch=ch,
                        role_summary=role_summary,
                        delta_serd=delta_serd, delta_baseline=delta_baseline)
    except Exception as exc:        # noqa: BLE001
        log.warning("figures render failed: %s", exc)

    # summary.json
    write_summary_json(out_dir, sim.sim_id, len(sim.agents),
                        getattr(sim, "n_ticks", 0),
                        pnl, priors_summary, serd_report=serd_report)

    return {
        "serd_report": serd_report,
        "role_summary": role_summary,
    }
