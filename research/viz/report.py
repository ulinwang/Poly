"""Build a single self-contained HTML report from output/<exp_id>/.

No server, no SPA. Reads the parquet/json/jsonl artifacts the runner
already wrote, renders 3 interactive Plotly charts + embeds the 6
static PNG figures + lists every LLM call (collapsible). The output
is `output/<exp_id>/report.html` — open it in any browser.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Optional

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from viz.charts import action_mix_per_tick, per_agent_pnl, yes_mid_trajectory


log = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# Hard cap on per-call response display so the HTML stays small even
# on long runs (180 calls × 5KB raw is fine, but truncation in the
# template caps each one at 6KB anyway).
_MAX_LLM_CALLS_RENDERED = 500


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",)),
        keep_trailing_newline=True,
    )


def _read_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception as exc:           # noqa: BLE001
        log.warning("could not read %s: %s", path, exc)
        return pd.DataFrame()


def _iter_jsonl(path: Path, limit: int = _MAX_LLM_CALLS_RENDERED) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit:
                return
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _personas_with_signals(
    personas_df: pd.DataFrame, positions_df: pd.DataFrame,
) -> list[dict]:
    """Combine agent_personas with per-agent private-signal info from
    the first-tick positions snapshot (no signal column in personas
    but the runner writes it on action rows)."""
    if personas_df.empty:
        return []
    out = personas_df.to_dict("records")
    # Wallet column isn't in agent_personas parquet (only sim_id, agent_id,
    # persona_type, risk_aversion, capital_initial, profile_text). Fill empty.
    for p in out:
        p.setdefault("wallet", "")
        p["private_signal_mu"] = None
        p["private_signal_sigma"] = None
    return out


def build_report(exp_dir: Path | str) -> Path:
    """Read `exp_dir` artifacts → write `exp_dir/report.html`. Returns
    the report path. Idempotent: overwrites any existing report."""
    exp_dir = Path(exp_dir)
    if not exp_dir.is_dir():
        raise FileNotFoundError(f"not a directory: {exp_dir}")

    # === Inputs (any may be missing — render placeholders gracefully) ===
    meta_path = exp_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"missing {meta_path}")
    meta = json.loads(meta_path.read_text())

    actions_df = _read_parquet(exp_dir / "raw" / "agent_actions.parquet")
    positions_df = _read_parquet(exp_dir / "raw" / "agent_positions.parquet")
    personas_df = _read_parquet(exp_dir / "raw" / "agent_personas.parquet")

    summary_path = exp_dir / "analysis" / "summary.json"
    summary: dict = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text())
        except json.JSONDecodeError:
            pass

    llm_calls = list(_iter_jsonl(exp_dir / "raw" / "llm_calls.jsonl"))

    # === Resolution outcome (from priors_summary in meta) ===
    priors = meta.get("priors_summary", {}) or {}
    winning_idx: Optional[int] = None
    if "winning_idx" in priors:
        winning_idx = int(priors["winning_idx"])
    elif "config" in meta:
        # Fall back: try to read priors_<slug>.json from the data/ dir
        slug = meta.get("config", {}).get("market", {}).get("slug")
        if slug:
            priors_path = Path("data") / f"priors_{slug}.json"
            if priors_path.exists():
                try:
                    raw = json.loads(priors_path.read_text())
                    winning_idx = int(raw.get("winning_idx", -1))
                    # also enrich priors block with the canonical values
                    priors.setdefault("signal_mu", raw.get("signal_mu"))
                    priors.setdefault("n_ticks", raw.get("n_ticks"))
                    priors.setdefault("tick_size", raw.get("tick_size"))
                    priors.setdefault("taker_fee_bps", raw.get("taker_fee_bps"))
                    priors.setdefault(
                        "bootstrap_source",
                        raw.get("bootstrap", {}).get("source", "unknown"),
                    )
                except Exception:           # noqa: BLE001
                    pass
    # Defensive defaults
    priors.setdefault("signal_mu", 0.0)
    priors.setdefault("n_ticks", 0)
    priors.setdefault("tick_size", 0.0)
    priors.setdefault("taker_fee_bps", 0.0)
    priors.setdefault("bootstrap_source", "unknown")

    # === Charts (Plotly HTML <div>s) ===
    price_div = yes_mid_trajectory(actions_df)
    pnl_div = per_agent_pnl(positions_df, personas_df, winning_idx)
    action_div = action_mix_per_tick(actions_df)

    # === Static figures (from the existing matplotlib pipeline) ===
    fig_dir = exp_dir / "figure"
    static_figures = (
        sorted(fig_dir.glob("*.png")) if fig_dir.is_dir() else []
    )

    # === Render template ===
    rendered = _env().get_template("report.html.j2").render(
        exp_id=meta.get("exp_id", exp_dir.name),
        meta=meta,
        priors=priors,
        winning_idx=winning_idx,
        pnl_summary=priors.get("pnl_summary") or summary.get("pnl_summary"),
        serd=summary.get("serd"),
        personas=_personas_with_signals(personas_df, positions_df),
        price_div=price_div,
        pnl_div=pnl_div,
        action_div=action_div,
        static_figures=static_figures,
        llm_calls=llm_calls,
    )

    out = exp_dir / "report.html"
    out.write_text(rendered, encoding="utf-8")
    log.info("wrote %s (%d KB, %d LLM calls)", out, out.stat().st_size // 1024,
             len(llm_calls))
    return out


def build_for_latest(output_dir: str | Path = "output") -> Path:
    """Find the most recently modified `output/<exp_id>/` and build
    its report. Useful for `python -m viz --latest`."""
    base = Path(output_dir)
    candidates = [
        d for d in base.iterdir() if d.is_dir() and (d / "meta.json").exists()
    ]
    if not candidates:
        raise FileNotFoundError(f"no exp dirs under {base}")
    latest = max(candidates, key=lambda d: d.stat().st_mtime)
    return build_report(latest)
