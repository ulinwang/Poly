"""Read-only experiment browser API.

Serves the completed simulation artifacts under output_v13/<suite>/ and
output/ so the frontend can:
  - list experiments (left sidebar)
  - show one experiment's parameters + metadata
  - plot every agent's wallet/holdings trajectory
  - drill into a single agent's trajectory + decision log

Each suite directory holds an index.json whose runs[].exp_id points to
the REAL result directory (dry-run stubs share the prefix but carry no
rows); we resolve through index.json so the explorer never reads an
empty stub.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = [ROOT / "output_v13", ROOT / "output"]

router = APIRouter(prefix="/api/experiments", tags=["explorer"])


# --------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------


def _discover() -> dict[str, dict]:
    """exp_id -> {dir, suite, name, slug, n_agents, n_ticks, status,
    started_at}. Resolved through each suite's index.json."""
    out: dict[str, dict] = {}
    for base in SEARCH_DIRS:
        if not base.exists():
            continue
        for idx_path in sorted(base.glob("*/index.json")):
            suite = idx_path.parent.name
            try:
                idx = json.loads(idx_path.read_text())
            except Exception:        # noqa: BLE001
                continue
            for run in idx.get("runs", []):
                eid = run.get("exp_id")
                if not eid:
                    continue
                d = idx_path.parent / eid
                meta_p = d / "meta.json"
                if not meta_p.exists():
                    continue
                try:
                    meta = json.loads(meta_p.read_text())
                except Exception:        # noqa: BLE001
                    continue
                cfg = meta.get("config", {})
                out[eid] = {
                    "exp_id": eid,
                    "dir": str(d),
                    "suite": suite,
                    "name": run.get("name", cfg.get("name", eid)),
                    "slug": cfg.get("market", {}).get("slug", ""),
                    "n_agents": meta.get("n_agents"),
                    "n_ticks": meta.get("n_ticks"),
                    "status": run.get("status", "ok"),
                    "started_at": meta.get("started_at"),
                }
    return out


def _registry(refresh: bool = False) -> dict[str, dict]:
    # tiny cache; refresh on demand if a new suite finished
    if refresh:
        _cached_registry.cache_clear()
    return _cached_registry()


@lru_cache(maxsize=1)
def _cached_registry() -> dict[str, dict]:
    return _discover()


def _entry(exp_id: str) -> dict:
    reg = _cached_registry()
    if exp_id not in reg:
        reg = _registry(refresh=True)
    if exp_id not in reg:
        raise HTTPException(404, f"experiment {exp_id!r} not found")
    return reg[exp_id]


def _raw(d: str, name: str) -> pd.DataFrame:
    p = Path(d) / "raw" / f"{name}.parquet"
    if not p.exists():
        raise HTTPException(404, f"{name}.parquet missing for this experiment")
    return pd.read_parquet(p)


# --------------------------------------------------------------------
# endpoints
# --------------------------------------------------------------------


@router.get("")
def list_experiments(refresh: bool = False):
    reg = _registry(refresh=refresh)
    rows = sorted(
        reg.values(),
        key=lambda r: (r["suite"], r["name"]),
    )
    # group by suite for the sidebar
    suites: dict[str, list] = {}
    for r in rows:
        suites.setdefault(r["suite"], []).append({
            k: r[k] for k in
            ("exp_id", "name", "slug", "n_agents", "n_ticks", "status")
        })
    return {"suites": suites, "total": len(rows)}


@router.get("/{exp_id}")
def experiment_meta(exp_id: str):
    e = _entry(exp_id)
    meta = json.loads((Path(e["dir"]) / "meta.json").read_text())
    cfg = meta.get("config", {})
    summary = {}
    sp = Path(e["dir"]) / "analysis" / "summary.json"
    if sp.exists():
        try:
            summary = json.loads(sp.read_text())
        except Exception:        # noqa: BLE001
            summary = {}
    # final market price from the action log
    final_yes_mid = None
    try:
        acts = _raw(e["dir"], "agent_actions").sort_values("tick_idx")
        if len(acts):
            final_yes_mid = float(acts["yes_mid_after"].iloc[-1])
    except HTTPException:
        pass
    return {
        "exp_id": exp_id,
        "suite": e["suite"],
        "name": e["name"],
        "slug": e["slug"],
        "n_agents": meta.get("n_agents"),
        "n_ticks": meta.get("n_ticks"),
        "started_at": meta.get("started_at"),
        "ended_at": meta.get("ended_at"),
        "sim_id": meta.get("sim_id"),
        "config": cfg,
        "priors_summary": meta.get("priors_summary", {}),
        "summary": summary,
        "final_yes_mid": final_yes_mid,
    }


@router.get("/{exp_id}/agents")
def experiment_agents(exp_id: str):
    e = _entry(exp_id)
    per = _raw(e["dir"], "agent_personas")
    pos = _raw(e["dir"], "agent_positions")
    acts = _raw(e["dir"], "agent_actions")
    last = (pos.sort_values("tick_idx")
               .groupby("agent_id").last().reset_index())
    act_n = acts.groupby("agent_id").size().to_dict()
    cancel_n = (acts[acts.action_type == "CANCEL"]
                .groupby("agent_id").size().to_dict())
    rows = []
    for _, r in per.sort_values("agent_id").iterrows():
        aid = int(r["agent_id"])
        lp = last[last.agent_id == aid]
        cash = float(lp["cash"].iloc[0]) if len(lp) else None
        ys = float(lp["yes_shares"].iloc[0]) if len(lp) else None
        ns = float(lp["no_shares"].iloc[0]) if len(lp) else None
        upnl = float(lp["unrealized_pnl"].iloc[0]) if len(lp) else None
        cap0 = float(r["capital_initial"])
        rows.append({
            "agent_id": aid,
            "persona_type": r["persona_type"],
            "capital_initial": cap0,
            "final_cash": cash,
            "yes_shares": ys,
            "no_shares": ns,
            "unrealized_pnl": upnl,
            "pnl": (None if cash is None else round(cash + (upnl or 0.0) - cap0, 2)),
            "n_actions": int(act_n.get(aid, 0)),
            "n_cancel": int(cancel_n.get(aid, 0)),
        })
    return {"exp_id": exp_id, "agents": rows}


@router.get("/{exp_id}/trajectories")
def experiment_trajectories(exp_id: str):
    """Per-agent net wallet value over ticks + the market price.
    net_value = cash + yes_shares*yes_mid + no_shares*no_mid (we use
    yes_mid for YES, (1-yes_mid) for NO as the binary-complement mid)."""
    e = _entry(exp_id)
    pos = _raw(e["dir"], "agent_positions").sort_values(["agent_id", "tick_idx"])
    acts = _raw(e["dir"], "agent_actions").sort_values("tick_idx")
    ymid = (acts.groupby("tick_idx")["yes_mid_after"].last())
    ticks = sorted(pos["tick_idx"].unique().tolist())
    mkt = [round(float(ymid.get(t, float("nan"))), 4) for t in ticks]
    agents: dict[int, dict] = {}
    for aid, g in pos.groupby("agent_id"):
        g = g.set_index("tick_idx")
        cash, val = [], []
        for t in ticks:
            if t in g.index:
                row = g.loc[t]
                ym = float(ymid.get(t, 0.5))
                c = float(row["cash"])
                nv = c + float(row["yes_shares"]) * ym \
                       + float(row["no_shares"]) * (1.0 - ym)
                cash.append(round(c, 2))
                val.append(round(nv, 2))
            else:
                cash.append(None)
                val.append(None)
        agents[int(aid)] = {"cash": cash, "net_value": val}
    return {"exp_id": exp_id, "ticks": ticks,
            "market_yes_mid": mkt, "agents": agents}


@router.get("/{exp_id}/agents/{agent_id}")
def agent_detail(exp_id: str, agent_id: int):
    e = _entry(exp_id)
    pos = (_raw(e["dir"], "agent_positions")
           .query("agent_id == @agent_id").sort_values("tick_idx"))
    acts = (_raw(e["dir"], "agent_actions")
            .query("agent_id == @agent_id").sort_values("tick_idx"))
    per = _raw(e["dir"], "agent_personas").query("agent_id == @agent_id")
    if not len(per):
        raise HTTPException(404, f"agent {agent_id} not in this experiment")
    pr = per.iloc[0]
    ymap = acts.groupby("tick_idx")["yes_mid_after"].last().to_dict()
    traj = []
    for _, r in pos.iterrows():
        t = int(r["tick_idx"])
        ym = float(ymap.get(t, 0.5))
        traj.append({
            "tick": t,
            "cash": round(float(r["cash"]), 2),
            "yes_shares": round(float(r["yes_shares"]), 2),
            "no_shares": round(float(r["no_shares"]), 2),
            "net_value": round(
                float(r["cash"]) + float(r["yes_shares"]) * ym
                + float(r["no_shares"]) * (1.0 - ym), 2),
            "yes_mid": round(ym, 4),
        })
    log = []
    for _, r in acts.iterrows():
        log.append({
            "tick": int(r["tick_idx"]),
            "action": r["action_type"],
            "outcome": r["outcome"],
            "side": r["side"],
            "price": round(float(r["price"]), 4),
            "size_usd": round(float(r["size_usd"]), 2),
            "n_fills": int(r["n_fills"]),
            "yes_mid_after": round(float(r["yes_mid_after"]), 4),
            "reasoning": (str(r["reasoning"]) or "").strip()[:600],
        })
    return {
        "exp_id": exp_id,
        "agent_id": agent_id,
        "persona_type": pr["persona_type"],
        "capital_initial": float(pr["capital_initial"]),
        "profile_text": str(pr["profile_text"]),
        "trajectory": traj,
        "decisions": log,
    }
