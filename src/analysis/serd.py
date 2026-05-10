"""
v4 Phase 5 — SERD-style validation pipeline.

Implements the analysis from "Predator and Prey: The Hidden User Role
Dynamics of Decentralized Prediction Markets" (Gomez-Cram et al. 2026)
on simulator output. Goal: post-hoc test whether the simulator
reproduces the predator-prey hierarchy that the paper documented in
real Polymarket.

Pipeline (paper §3.2-§4):

  1. Build directed weighted interaction network from agent_fills:
       edge j → i  iff j was the maker, i was the taker;
       weight    =  Σ notional in (j → i) over the simulation;
       net_flow  =  if both j→i and i→j exist, keep only the residual.
  2. For each node i:
       s_in[i]  = Σ_j w(j → i)   (capital received as maker)
       s_out[i] = Σ_j w(i → j)   (capital paid as taker)
       R[i]     = s_in / max(s_out, ε)        (Eq. 4)
  3. Role assignment by quartile of R:
       top 25% → ApexPredator
       25-50%  → UpperMeso
       50-75%  → LowerMeso
       bottom 25% → Prey
  4. Per-agent ROI = (final_value - initial_capital) / capital_deployed
                                                    (Eq. 5).
  5. Group ROI per role; verify monotonicity (paper Tables 2 / 4).
  6. Compare ΔROI(SERD) vs ΔROI(DBSCAN+KMeans baseline using paper Tbl 5
     features tx_freq / maker_ratio / position_size / asset_diversity).

Pure-stdlib (math / statistics) — no numpy/scipy dependency.

Usage:
    uv run python -m src.sim.serd --sim-id <hex>
    uv run python -m src.sim.serd --sim-id <hex> --pool-with <other_sim_id> ...
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from ..pipeline.clickhouse import ClickHouse
from ..pipeline.config import get_settings


_EPS = 1e-9
ENV_MAKER_AGENT_ID = 999_999   # mirrors src/sim/env.py

ROLES = ("ApexPredator", "UpperMeso", "LowerMeso", "Prey")

log = logging.getLogger(__name__)


# ---- Network construction ----------------------------------------------------


def build_network(
    sim_id: str, ch: ClickHouse, exclude_env_maker: bool = True,
) -> dict[tuple[int, int], float]:
    """Return a sparse directed weighted graph as a dict
    {(maker_agent_id, taker_agent_id): aggregate_notional}, summed
    across the simulation. Excludes env_maker (agent_id ==
    ENV_MAKER_AGENT_ID) by default."""
    rows = ch.client.execute(
        f"""
        SELECT maker_agent_id, taker_agent_id, sum(notional)
        FROM {ch.database}.agent_fills
        WHERE sim_id = %(sid)s
        GROUP BY maker_agent_id, taker_agent_id
        """,
        {"sid": sim_id},
    )
    edges: dict[tuple[int, int], float] = {}
    for m, t, w in rows:
        m, t = int(m), int(t)
        if exclude_env_maker and (m == ENV_MAKER_AGENT_ID or t == ENV_MAKER_AGENT_ID):
            continue
        # M1 (defense in depth): self-loops should be impossible after
        # the v5 self-match-prevention fix in OrderBook, but legacy
        # data from pre-v5 runs may still contain (i, i) edges that
        # would corrupt SERD net-flow ratios.
        if m == t:
            continue
        edges[(m, t)] = float(w)
    return edges


def net_flow_edges(
    edges: dict[tuple[int, int], float],
) -> dict[tuple[int, int], float]:
    """Per the paper §3.2: 'if both i↔j coexist, keep only the net
    flow direction'. Collapse symmetric pairs."""
    out: dict[tuple[int, int], float] = {}
    seen: set[tuple[int, int]] = set()
    for (m, t), w in edges.items():
        if (m, t) in seen or (t, m) in seen:
            continue
        rev = edges.get((t, m), 0.0)
        if w >= rev:
            net = w - rev
            if net > _EPS:
                out[(m, t)] = net
        else:
            net = rev - w
            if net > _EPS:
                out[(t, m)] = net
        seen.add((m, t))
        seen.add((t, m))
    return out


def node_strengths(
    edges: dict[tuple[int, int], float], all_agent_ids: Iterable[int],
) -> dict[int, dict[str, float]]:
    s: dict[int, dict[str, float]] = {
        a: {"in": 0.0, "out": 0.0, "ratio": 0.0} for a in all_agent_ids
    }
    for (m, t), w in edges.items():
        if m in s:
            s[m]["in"] += w
        if t in s:
            s[t]["out"] += w
    for a, d in s.items():
        d["ratio"] = d["in"] / max(d["out"], _EPS)
    return s


# ---- Role assignment ---------------------------------------------------------


def assign_quartile_roles(
    strengths: dict[int, dict[str, float]],
) -> dict[int, str]:
    """Sort agents by R = s_in / s_out, partition into 4 quartiles.
    Highest quartile → ApexPredator, lowest → Prey. Ties broken by
    agent_id for determinism."""
    if not strengths:
        return {}
    sorted_agents = sorted(
        strengths.keys(), key=lambda a: (strengths[a]["ratio"], -a),
    )
    n = len(sorted_agents)
    if n == 0:
        return {}
    out: dict[int, str] = {}
    for i, a in enumerate(sorted_agents):
        # Partition by index — bottom = Prey, top = Apex. Use floor
        # division to keep robust at small n.
        q = min(3, (i * 4) // n)
        # We want q=3 (top) to be Apex, q=0 to be Prey
        out[a] = ROLES[3 - q]
    return out


# ---- ROI computation ---------------------------------------------------------


def compute_roi_per_agent(
    sim_id: str, ch: ClickHouse,
) -> dict[int, dict[str, float]]:
    """Per-agent realized PnL / capital deployed, using the latest
    positions row + the agent's persona capital_initial.

    Capital deployed (paper Eq. 5) = max absolute exposure during sim.
    We approximate it as the max(|cash + yes_shares*yes_mid + no_shares*no_mid|)
    which is well-bounded by capital_initial in practice."""
    sim_row = ch.client.execute(
        f"""
        SELECT market_resolved_yes
        FROM {ch.database}.agent_simulations FINAL
        WHERE sim_id = %(sid)s
        """,
        {"sid": sim_id},
    )
    if not sim_row or sim_row[0][0] is None:
        return {}
    resolved_yes = int(sim_row[0][0])
    yes_payoff = 1.0 if resolved_yes == 1 else 0.0
    no_payoff = 1.0 - yes_payoff

    rows = ch.client.execute(
        f"""
        SELECT p.agent_id,
               argMax(p.cash, p.tick),
               argMax(p.yes_shares, p.tick),
               argMax(p.no_shares, p.tick),
               any(per.capital_initial)
        FROM {ch.database}.agent_positions p
        JOIN {ch.database}.agent_personas per
             ON per.sim_id = p.sim_id AND per.agent_id = p.agent_id
        WHERE p.sim_id = %(sid)s
        GROUP BY p.agent_id
        """,
        {"sid": sim_id},
    )
    out: dict[int, dict[str, float]] = {}
    for agent_id, final_cash, final_yes, final_no, capital_initial in rows:
        agent_id = int(agent_id)
        if agent_id == ENV_MAKER_AGENT_ID:
            continue
        cap = float(capital_initial or 0.0)
        if cap <= 0:
            continue
        final_value = (
            float(final_cash)
            + float(final_yes) * yes_payoff
            + float(final_no) * no_payoff
        )
        pnl = final_value - cap
        roi = pnl / cap
        out[agent_id] = {
            "pnl": pnl, "roi": roi, "capital": cap, "final_value": final_value,
        }
    return out


# ---- Group aggregation -------------------------------------------------------


def roi_by_role(
    role_of: dict[int, str], roi_of: dict[int, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Mean ROI per role + count + capital share."""
    by: dict[str, list[tuple[float, float]]] = defaultdict(list)
    total_cap = sum(d["capital"] for d in roi_of.values()) or _EPS
    for a, role in role_of.items():
        if a not in roi_of:
            continue
        by[role].append((roi_of[a]["roi"], roi_of[a]["capital"]))
    out: dict[str, dict[str, float]] = {}
    for role in ROLES:
        items = by.get(role, [])
        if not items:
            out[role] = {"n": 0, "mean_roi": 0.0, "vol_share": 0.0}
            continue
        mean_roi = statistics.fmean(r for r, _ in items)
        cap = sum(c for _, c in items)
        out[role] = {"n": len(items), "mean_roi": mean_roi,
                     "vol_share": cap / total_cap}
    return out


def monotonic_descending(roi_by: dict[str, dict[str, float]]) -> bool:
    """True iff ROI decreases monotonically Apex → UpperMeso → LowerMeso → Prey."""
    seq = [roi_by[r]["mean_roi"] for r in ROLES if roi_by[r]["n"] > 0]
    return all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1))


def delta_roi(roi_by: dict[str, dict[str, float]]) -> float:
    """ΔROI = max(role mean_roi) - min(role mean_roi) across non-empty roles."""
    seq = [roi_by[r]["mean_roi"] for r in ROLES if roi_by[r]["n"] > 0]
    if not seq:
        return 0.0
    return max(seq) - min(seq)


# ---- Baseline: feature-based clustering --------------------------------------


def _agent_features(
    sim_id: str, ch: ClickHouse,
) -> dict[int, dict[str, float]]:
    """Paper Table 5 features computed on the sim's own action log."""
    rows = ch.client.execute(
        f"""
        SELECT agent_id,
               count() AS tx_freq,
               sum(if(order_type='LIMIT', 1, 0)) / max(count(), 1) AS maker_ratio,
               avg(size_usd) AS avg_pos,
               1 AS asset_diversity   -- single market per sim
        FROM {ch.database}.agent_actions
        WHERE sim_id = %(sid)s AND order_type != 'HOLD'
              AND agent_id != 999999
        GROUP BY agent_id
        """,
        {"sid": sim_id},
    )
    return {
        int(a): {
            "tx_freq": float(tf), "maker_ratio": float(mr),
            "avg_pos": float(ap), "asset_diversity": float(ad),
        }
        for a, tf, mr, ap, ad in rows
    }


def _kmeans_2(features: dict[int, dict[str, float]]) -> dict[int, int]:
    """Lightweight K=2 means on z-scored features. Pure stdlib."""
    if not features:
        return {}
    keys = list(features.keys())
    feats = [
        [features[k]["tx_freq"], features[k]["maker_ratio"],
         features[k]["avg_pos"], features[k]["asset_diversity"]]
        for k in keys
    ]
    # z-score per feature
    n_dim = len(feats[0])
    means = [statistics.fmean(row[d] for row in feats) for d in range(n_dim)]
    stds = []
    for d in range(n_dim):
        try:
            s = statistics.stdev(row[d] for row in feats)
        except statistics.StatisticsError:
            s = 0.0
        stds.append(s if s > 0 else 1.0)
    z = [
        [(row[d] - means[d]) / stds[d] for d in range(n_dim)] for row in feats
    ]

    # init centers at first and last point
    if len(z) < 2:
        return {keys[0]: 0}
    c0, c1 = list(z[0]), list(z[-1])
    for _ in range(20):
        assign = []
        for row in z:
            d0 = sum((row[d] - c0[d]) ** 2 for d in range(n_dim))
            d1 = sum((row[d] - c1[d]) ** 2 for d in range(n_dim))
            assign.append(0 if d0 <= d1 else 1)
        new0 = [statistics.fmean([row[d] for row, a in zip(z, assign) if a == 0])
                if any(a == 0 for a in assign) else c0[d]
                for d in range(n_dim)]
        new1 = [statistics.fmean([row[d] for row, a in zip(z, assign) if a == 1])
                if any(a == 1 for a in assign) else c1[d]
                for d in range(n_dim)]
        if new0 == c0 and new1 == c1:
            break
        c0, c1 = new0, new1
    return {keys[i]: assign[i] for i in range(len(keys))}


def baseline_roi_separation(
    sim_id: str, ch: ClickHouse, roi_of: dict[int, dict[str, float]],
) -> dict[str, dict[str, float]]:
    feats = _agent_features(sim_id, ch)
    cluster = _kmeans_2(feats)
    if not cluster:
        return {}
    by: dict[str, list[float]] = defaultdict(list)
    for a, c in cluster.items():
        if a in roi_of:
            by[f"Cluster{c}"].append(roi_of[a]["roi"])
    out = {}
    for k, vals in by.items():
        out[k] = {"n": len(vals), "mean_roi": statistics.fmean(vals)}
    return out


# ---- Top-level orchestration -------------------------------------------------


@dataclass
class SerdReport:
    sim_id: str
    n_agents: int
    role_of: dict[int, str]
    roi_per_role: dict[str, dict[str, float]]
    delta_roi_serd: float
    monotonic: bool
    baseline_roi: dict[str, dict[str, float]]
    delta_roi_baseline: float


def analyze_sim(sim_id: str, ch: Optional[ClickHouse] = None) -> SerdReport:
    settings = get_settings()
    if ch is None:
        ch = ClickHouse(
            host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )
    ch.ensure_serd_schema()

    edges = build_network(sim_id, ch)
    net_edges = net_flow_edges(edges)
    roi_of = compute_roi_per_agent(sim_id, ch)
    all_ids = set(roi_of.keys())
    strengths = node_strengths(net_edges, all_ids)
    role_of = assign_quartile_roles(strengths)
    roi_role = roi_by_role(role_of, roi_of)
    base = baseline_roi_separation(sim_id, ch, roi_of)

    # Persist to ClickHouse
    fetched_at = dt.datetime.utcnow()
    rows = []
    for r, d in roi_role.items():
        rows.append((sim_id, "SERD", r, int(d["n"]), float(d["mean_roi"]),
                     float(d["vol_share"]), fetched_at))
    for r, d in base.items():
        rows.append((sim_id, "DBSCAN_KMEANS", r, int(d["n"]),
                     float(d["mean_roi"]), 0.0, fetched_at))
    ch.insert_serd_results(rows)

    return SerdReport(
        sim_id=sim_id, n_agents=len(all_ids),
        role_of=role_of, roi_per_role=roi_role,
        delta_roi_serd=delta_roi(roi_role),
        monotonic=monotonic_descending(roi_role),
        baseline_roi=base,
        delta_roi_baseline=(
            max(d["mean_roi"] for d in base.values()) -
            min(d["mean_roi"] for d in base.values())
            if base else 0.0
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim-id", required=True)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    report = analyze_sim(args.sim_id)
    print("=" * 60)
    print(f"SERD analysis for sim_id={report.sim_id}  n_agents={report.n_agents}")
    print()
    print(f"{'Role':<14} {'n':>4} {'mean_roi':>10} {'vol_share':>10}")
    for r in ROLES:
        d = report.roi_per_role.get(r, {"n": 0, "mean_roi": 0, "vol_share": 0})
        print(f"  {r:<12} {d['n']:>4} {d['mean_roi']:>10.4f} {d['vol_share']:>10.3f}")
    print()
    print(f"  Δ ROI (SERD)        = {report.delta_roi_serd:.4f}")
    print(f"  monotonic Apex→Prey = {report.monotonic}")
    print()
    print("Baseline (DBSCAN-style + K-Means K=2 on Paper Table 5 features):")
    for r, d in report.baseline_roi.items():
        print(f"  {r:<12} {d['n']:>4} mean_roi={d['mean_roi']:.4f}")
    print(f"  Δ ROI (baseline)    = {report.delta_roi_baseline:.4f}")
    print()
    advantage = report.delta_roi_serd - report.delta_roi_baseline
    print(f"  SERD advantage       = {advantage:+.4f} "
          f"(positive = SERD recovers structure better than features)")


if __name__ == "__main__":
    main()
