"""Maker→taker capital-flow network analysis.

Build a directed weighted graph from `agent_fills` where each edge
(m → t) carries the cumulative notional flowing from agent `m` (the
resting/maker side) to agent `t` (the aggressing/taker side).

Public API:
    build_network(fills_df, exclude_env_maker=True) -> networkx.DiGraph
    network_metrics(g) -> pd.DataFrame
    render_network(g, out_path, persona_of=None, ...) -> Path

Filters: by default we drop the synthetic bootstrap maker (agent_id =
999_999) which is an environment artifact, not an actual strategic
participant. Self-loops (m == t) are also removed.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd


ENV_MAKER_AGENT_ID = 999_999


def build_network(
    fills_df: pd.DataFrame, exclude_env_maker: bool = True,
) -> nx.DiGraph:
    """Aggregate fills into a directed weighted graph.

    Edge weight = sum of `notional` across all fills (m, t).
    """
    if fills_df.empty:
        return nx.DiGraph()
    df = fills_df.copy()
    if exclude_env_maker:
        df = df[
            (df["maker_agent_id"] != ENV_MAKER_AGENT_ID)
            & (df["taker_agent_id"] != ENV_MAKER_AGENT_ID)
        ]
    df = df[df["maker_agent_id"] != df["taker_agent_id"]]
    if df.empty:
        return nx.DiGraph()

    agg = (
        df.groupby(["maker_agent_id", "taker_agent_id"])["notional"]
        .sum().reset_index()
    )
    g = nx.DiGraph()
    for _, r in agg.iterrows():
        m = int(r["maker_agent_id"])
        t = int(r["taker_agent_id"])
        w = float(r["notional"])
        if w > 0:
            g.add_edge(m, t, weight=w)
    return g


def network_metrics(g: nx.DiGraph) -> pd.DataFrame:
    """Per-node metrics: strength_in/out, ratio (a la SERD), degree."""
    if g.number_of_nodes() == 0:
        return pd.DataFrame()
    rows = []
    for n in g.nodes():
        s_in = sum(d["weight"] for _, _, d in g.in_edges(n, data=True))
        s_out = sum(d["weight"] for _, _, d in g.out_edges(n, data=True))
        rows.append({
            "agent_id": n,
            "in_degree": g.in_degree(n),
            "out_degree": g.out_degree(n),
            "strength_in": s_in,
            "strength_out": s_out,
            "strength_ratio": s_in / max(s_out, 1e-9),
            "net_flow": s_in - s_out,
        })
    df = pd.DataFrame(rows).sort_values("strength_ratio", ascending=False)
    return df


def role_quartile(metrics: pd.DataFrame) -> pd.Series:
    """SERD-style quartile role labels from strength_ratio.

    Top 25% → ApexPredator, 25-50% → UpperMeso, 50-75% → LowerMeso,
    bottom 25% → Prey. Returns a Series indexed by agent_id.
    """
    if metrics.empty:
        return pd.Series(dtype=str)
    ranked = metrics.sort_values("strength_ratio", ascending=False)
    n = len(ranked)
    labels = []
    for i, _ in enumerate(ranked.itertuples()):
        if i < n / 4:
            labels.append("ApexPredator")
        elif i < n / 2:
            labels.append("UpperMeso")
        elif i < 3 * n / 4:
            labels.append("LowerMeso")
        else:
            labels.append("Prey")
    ranked = ranked.copy()
    ranked["role"] = labels
    return ranked.set_index("agent_id")["role"]


_ROLE_COLOR = {
    "ApexPredator": "#aa1111",
    "UpperMeso":    "#dd7733",
    "LowerMeso":    "#3377aa",
    "Prey":         "#1144aa",
    None:           "#888888",
}


def render_network(
    g: nx.DiGraph, out_path: Path,
    persona_of: Optional[dict[int, str]] = None,
    title: str = "Maker → taker capital-flow network",
    figsize: tuple = (9, 7),
) -> Path:
    """Render a matplotlib network plot with node size ∝ total strength
    and color by SERD role quartile."""
    if g.number_of_nodes() == 0:
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "no edges to render", ha="center", va="center",
                transform=ax.transAxes, color="grey")
        ax.set_axis_off()
        fig.savefig(out_path, dpi=160, bbox_inches="tight")
        plt.close(fig)
        return out_path

    metrics = network_metrics(g)
    roles = role_quartile(metrics)

    fig, ax = plt.subplots(figsize=figsize)
    pos = nx.spring_layout(g, k=0.8, seed=42, iterations=80)

    # Node sizes ∝ total strength
    sizes = []
    colors = []
    for n in g.nodes():
        m_row = metrics[metrics["agent_id"] == n].iloc[0]
        s = m_row["strength_in"] + m_row["strength_out"]
        sizes.append(120 + 6 * math.sqrt(max(s, 1.0)))
        colors.append(_ROLE_COLOR[roles.get(n)])

    # Edges: width ∝ log(weight); color by direction (darker = bigger)
    weights = [d["weight"] for _, _, d in g.edges(data=True)]
    max_w = max(weights) if weights else 1.0
    widths = [0.4 + 2.5 * math.log1p(w) / math.log1p(max_w) for w in weights]
    alphas = [0.25 + 0.55 * (w / max_w) for w in weights]

    nx.draw_networkx_edges(
        g, pos, ax=ax,
        width=widths, alpha=0.5,
        edge_color="#444444",
        arrows=True, arrowsize=10, arrowstyle="-|>",
        connectionstyle="arc3,rad=0.08",
    )
    nx.draw_networkx_nodes(g, pos, ax=ax, node_size=sizes, node_color=colors,
                            edgecolors="#222222", linewidths=0.8, alpha=0.95)
    nx.draw_networkx_labels(g, pos, ax=ax,
                             labels={n: str(n) for n in g.nodes()},
                             font_size=8, font_color="white")

    # Legend
    legend_elems = []
    for role, c in _ROLE_COLOR.items():
        if role is None or role not in roles.values:
            continue
        legend_elems.append(plt.Line2D([0], [0], marker="o", color="w",
            markerfacecolor=c, markeredgecolor="#222", markersize=9,
            label=role))
    if legend_elems:
        ax.legend(handles=legend_elems, loc="upper right", fontsize=9,
                  framealpha=0.9)

    ax.set_title(title)
    ax.set_axis_off()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out_path


def render_flow_heatmap(
    g: nx.DiGraph, out_path: Path,
    title: str = "Capital flow heatmap (maker → taker)",
    figsize: tuple = (7, 6),
) -> Path:
    """Heatmap of the flow matrix sorted by total strength."""
    if g.number_of_nodes() == 0:
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "no edges", ha="center", va="center")
        fig.savefig(out_path, dpi=160, bbox_inches="tight")
        plt.close(fig)
        return out_path
    metrics = network_metrics(g)
    nodes = (metrics.assign(total=metrics["strength_in"] + metrics["strength_out"])
             .sort_values("total", ascending=False)["agent_id"].tolist())
    idx = {n: i for i, n in enumerate(nodes)}
    mat = np.zeros((len(nodes), len(nodes)))
    for u, v, d in g.edges(data=True):
        mat[idx[u], idx[v]] = d["weight"]

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(np.log1p(mat), cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(nodes)))
    ax.set_yticks(range(len(nodes)))
    ax.set_xticklabels([str(n) for n in nodes], rotation=90, fontsize=7)
    ax.set_yticklabels([str(n) for n in nodes], fontsize=7)
    ax.set_xlabel("taker (recipient of flow)")
    ax.set_ylabel("maker (origin of flow)")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, shrink=0.7, label="log(1 + notional $)")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out_path
