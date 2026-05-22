"""Additional thesis figures + table CSVs from committed sim artifacts.

Nature-style rendering matched to scripts/thesis_figures.py via the
shared scripts/_thesis_style.py preamble.

Figures (saved as PNG + SVG + PDF + 600dpi TIFF + sibling CSV):
  fig8_archetype_radar    — K=4 archetype centroid radar (7 features)
  fig9_network_b6         — B6 maker–taker network, control vs rumor
  fig10_b1_normalized     — B1 ten markets normalized price trajectories
  fig11_b4_pnl_kde        — B4 per-agent P&L histograms, on vs off
  fig12_action_mix_groups — action-mix stacked bar across 8 groups

Tables (CSV under docs/v13/tables/):
  table6_action_mix.csv
  table7_b1_markets.csv
  table8_b3_archetype_pnl.csv

Run:  uv run python scripts/thesis_extra_artifacts.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

from _thesis_style import (
    apply_style, finalize, fig_size, panel_label,
    BLUE, BLUE_LIGHT, GREEN, GREEN_DEEP, RED, RED_LIGHT,
    NEUTRAL_LIGHT, NEUTRAL_MID, NEUTRAL_DARK, NEUTRAL_BLACK,
    TEAL, VIOLET, GOLD,
    COL_SINGLE_MM, COL_DOUBLE_MM,
)

apply_style()

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "docs" / "v13" / "figures"
TBL = ROOT / "docs" / "v13" / "tables"
FIG.mkdir(parents=True, exist_ok=True)
TBL.mkdir(parents=True, exist_ok=True)

ACTIONS = ["LIMIT", "MARKET", "CANCEL", "HOLD", "SPLIT", "MERGE", "UPDATE_BELIEF"]
ACTION_LABEL_EN = {
    "LIMIT": "limit", "MARKET": "market", "CANCEL": "cancel",
    "HOLD": "hold", "SPLIT": "split", "MERGE": "merge",
    "UPDATE_BELIEF": "belief",
}
# Distinct grayscale + signal-blue accent for action layers
ACTION_COLOR = {
    "LIMIT": NEUTRAL_DARK,
    "MARKET": NEUTRAL_MID,
    "CANCEL": NEUTRAL_LIGHT,
    "HOLD": "#E8E8E8",
    "SPLIT": "#A3A3A3",
    "MERGE": "#5C5C5C",
    "UPDATE_BELIEF": BLUE,
}


def _eid(suite, name):
    idx = json.loads((ROOT / f"output/v13/{suite}/index.json").read_text())
    for r in idx["runs"]:
        if r["name"] == name:
            return r["exp_id"]
    raise KeyError(name)


def _acts(suite, name):
    return pd.read_parquet(
        ROOT / f"output/v13/{suite}/{_eid(suite, name)}/raw/agent_actions.parquet"
    )


def _fills(suite, name):
    return pd.read_parquet(
        ROOT / f"output/v13/{suite}/{_eid(suite, name)}/raw/agent_fills.parquet"
    )


def _positions_pnl(suite, name):
    eid = _eid(suite, name)
    per = pd.read_parquet(ROOT / f"output/v13/{suite}/{eid}/raw/agent_personas.parquet")
    pos = pd.read_parquet(ROOT / f"output/v13/{suite}/{eid}/raw/agent_positions.parquet")
    last = pos.sort_values("tick_idx").groupby("agent_id").last().reset_index()
    m = last.merge(per[["agent_id", "capital_initial", "persona_type"]],
                   on="agent_id")
    m["pnl"] = m["cash"] + m["unrealized_pnl"] - m["capital_initial"]
    return m


# ----------------------------------------------------------------------
# Fig 8 — four-archetype centroid radar
# ----------------------------------------------------------------------

def fig_archetype_radar():
    p = ROOT / "data/clustering/cluster_profiles_20230523T153721Z.json"
    d = json.loads(p.read_text())
    feats = d["feat_cols"]
    raw = np.array([[d["clusters"][str(k)]["centroid"][f] for f in feats]
                    for k in range(d["K"])])
    mn, mx = raw.min(axis=0), raw.max(axis=0)
    norm = (raw - mn) / np.where(mx - mn > 0, mx - mn, 1.0)
    feat_labels = [
        "log\nnotional", "market\nshare", "markets\nper $",
        "mean\nprice", "tail\ntrades", "active\ndays", "price\nstd",
    ]
    angles = np.linspace(0, 2 * np.pi, len(feats), endpoint=False).tolist()
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM + 20, 95),
                           subplot_kw=dict(polar=True))
    colors = [BLUE, GREEN_DEEP, RED, VIOLET]
    for k in range(d["K"]):
        v = norm[k].tolist() + [norm[k][0]]
        pct = d["clusters"][str(k)]["pct"] * 100
        ax.plot(angles, v, lw=1.0, color=colors[k],
                marker="o", ms=2.5, label=f"A{k+1} ({pct:.1f}%)")
        ax.fill(angles, v, color=colors[k], alpha=0.10)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(feat_labels, fontsize=6.5)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["", "0.5", "", "1.0"], fontsize=6, color=NEUTRAL_MID)
    ax.tick_params(pad=2)
    ax.set_rlabel_position(0)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.18), ncol=4,
              fontsize=6.5, columnspacing=1.2)
    df = pd.DataFrame(raw, columns=feats)
    df.insert(0, "archetype", [f"A{k+1}" for k in range(d["K"])])
    df["pct"] = [d["clusters"][str(k)]["pct"] for k in range(d["K"])]
    finalize(fig, FIG / "fig8_archetype_radar", source_data=df)


# ----------------------------------------------------------------------
# Fig 9 — B6 maker-taker network — control vs rumor
# ----------------------------------------------------------------------

def fig_network_b6():
    import sys
    sys.path.insert(0, str(ROOT))
    from experiments.analysis.network import build_network
    fig, axes = plt.subplots(1, 2, figsize=fig_size(COL_DOUBLE_MM, 95))
    for ax, name, lbl in [(axes[0], "b6_control_s0", "a"),
                          (axes[1], "b6_rumor_s0", "b")]:
        f = _fills("b6", name)
        g = build_network(f, exclude_env_maker=True)
        if g.number_of_edges() == 0:
            ax.text(0.5, 0.5, "no flow", ha="center", va="center")
            continue
        pos = nx.spring_layout(g, seed=0,
            k=1.5 / np.sqrt(max(1, g.number_of_nodes())))
        weights = np.array([d["weight"] for *_, d in g.edges(data=True)])
        wnorm = 0.3 + 1.6 * (weights / weights.max())
        node_size = [40 + 0.03 * g.degree(n, weight="weight") for n in g.nodes()]
        nx.draw_networkx_edges(g, pos, ax=ax, alpha=0.45,
                               width=wnorm, edge_color=NEUTRAL_MID,
                               arrows=True, arrowsize=4,
                               connectionstyle="arc3,rad=0.06")
        nx.draw_networkx_nodes(g, pos, ax=ax, node_size=node_size,
                               node_color=BLUE if name.endswith("rumor_s0") else NEUTRAL_LIGHT,
                               edgecolors=NEUTRAL_BLACK, linewidths=0.5,
                               alpha=0.9)
        ax.set_title("control" if lbl == "a" else "rumor",
                     fontsize=7, color=NEUTRAL_DARK)
        panel_label(ax, lbl, x=0.0, y=1.02)
        ax.axis("off")
    finalize(fig, FIG / "fig9_network_b6", source_data=None)


# ----------------------------------------------------------------------
# Fig 10 — B1 ten markets normalized trajectories
# ----------------------------------------------------------------------

def fig_b1_normalized():
    idx = json.loads((ROOT / "output/v13/b1/index.json").read_text())
    rows = []
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM + 20, 65))
    for r in idx["runs"]:
        a = pd.read_parquet(
            ROOT / f"output/v13/b1/{r['exp_id']}/raw/agent_actions.parquet"
        ).sort_values("tick_idx")
        s = a.groupby("tick_idx")["yes_mid_after"].last()
        y = s.values - float(a["yes_mid_before"].iloc[0])
        x = np.arange(len(y)) / max(len(y) - 1, 1)
        # truth direction: positive (toward 1) or negative (toward 0)
        # the b1 config has winning_idx in market metadata, but we proxy from
        # final true outcome implied by the b1_metrics.csv -> look up.
        ax.plot(x, y, color=NEUTRAL_MID, alpha=0.55, lw=0.8,
                marker="o", ms=1.6)
        for xi, yi in zip(x, y):
            rows.append({"market": r["name"][:32],
                         "rel_round": float(xi), "delta_yes_mid": float(yi)})
    ax.axhline(0, color=NEUTRAL_MID, ls="--", lw=0.6)
    ax.set_xlabel("relative round  (0 = start, 1 = settlement)")
    ax.set_ylabel("YES mid-price change vs start")
    finalize(fig, FIG / "fig10_b1_normalized", source_data=pd.DataFrame(rows))


# ----------------------------------------------------------------------
# Fig 11 — B4 individual P&L histogram, belief on vs off
# ----------------------------------------------------------------------

def fig_b4_pnl_kde():
    off, on = [], []
    for s in (0, 1, 2):
        off += _positions_pnl("b4", f"b4_belief_off_s{s}")["pnl"].tolist()
        on += _positions_pnl("b4", f"b4_belief_on_s{s}")["pnl"].tolist()
    off = np.array(off); on = np.array(on)
    bins = np.linspace(min(off.min(), on.min()),
                       max(off.max(), on.max()), 36)
    fig, ax = plt.subplots(figsize=fig_size(COL_SINGLE_MM + 10, 60))
    ax.hist(off, bins=bins, color=NEUTRAL_LIGHT, edgecolor=NEUTRAL_BLACK,
            linewidth=0.4, alpha=0.9, label=f"belief off  (n={len(off)})")
    ax.hist(on, bins=bins, edgecolor=BLUE, lw=1.2,
            label=f"belief on   (n={len(on)})", histtype="step")
    ax.axvline(0, color=NEUTRAL_MID, ls="--", lw=0.6)
    ax.set_xlabel("individual agent P&L (USD)")
    ax.set_ylabel("agent count")
    ax.legend(loc="upper right", fontsize=6.5)
    df = pd.DataFrame({
        "condition": ["off"] * len(off) + ["on"] * len(on),
        "pnl": np.concatenate([off, on]),
    })
    finalize(fig, FIG / "fig11_b4_pnl_kde", source_data=df)


# ----------------------------------------------------------------------
# Fig 12 + table 6: action mix across 8 treatment groups
# ----------------------------------------------------------------------

GROUPS = [
    ("baseline", [("b2", f"b2_s{s}") for s in (0, 1, 2)]),
    ("archetype", [("b3", f"b3_archetype_s{s}") for s in (0, 1, 2)]),
    ("marginal", [("b3", f"b3_marginal_s{s}") for s in (0, 1, 2)]),
    ("uniform", [("b3", f"b3_uniform_s{s}") for s in (0, 1, 2)]),
    ("belief off", [("b4", f"b4_belief_off_s{s}") for s in (0, 1, 2)]),
    ("belief on", [("b4", f"b4_belief_on_s{s}") for s in (0, 1, 2)]),
    ("control", [("b6", f"b6_control_s{s}") for s in (0, 1, 2)]),
    ("rumor", [("b6", f"b6_rumor_s{s}") for s in (0, 1, 2)]),
]


def _group_mix(runs):
    counts = {a: 0 for a in ACTIONS}
    total = 0
    for suite, name in runs:
        a = _acts(suite, name)
        for k, v in a["action_type"].value_counts().items():
            counts[k] = counts.get(k, 0) + int(v); total += int(v)
    return {a: 100.0 * counts.get(a, 0) / max(total, 1) for a in ACTIONS}


def fig_action_mix_groups():
    rows = [{"group": label, **_group_mix(runs)} for label, runs in GROUPS]
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=fig_size(COL_DOUBLE_MM, 70))
    bottom = np.zeros(len(df))
    for a in ACTIONS:
        ax.bar(df["group"], df[a], bottom=bottom, label=ACTION_LABEL_EN[a],
               color=ACTION_COLOR[a], edgecolor=NEUTRAL_BLACK, linewidth=0.3)
        bottom += df[a].values
    ax.set_ylabel("share of all actions (%)")
    ax.set_ylim(0, 100)
    ax.legend(ncol=7, bbox_to_anchor=(0.5, -0.20), loc="upper center",
              fontsize=6.5, columnspacing=1.0, handletextpad=0.4)
    # direct annotation for the belief-on group's belief share
    on_idx = list(df["group"]).index("belief on")
    on_belief = df.loc[on_idx, "UPDATE_BELIEF"]
    ax.text(on_idx, df.loc[on_idx, "LIMIT":"MERGE"].sum() +
            on_belief / 2,
            f"belief\n{on_belief:.0f}%",
            ha="center", va="center", fontsize=6, color="white",
            fontweight="bold")
    finalize(fig, FIG / "fig12_action_mix_groups", source_data=df)
    # Also write Chinese-labeled CSV for the thesis table
    zh_label = {"LIMIT": "限价单", "MARKET": "市价单", "CANCEL": "撤单",
                "HOLD": "不操作", "SPLIT": "拆分", "MERGE": "合并",
                "UPDATE_BELIEF": "声明信念"}
    zh_group = {"baseline": "基线", "archetype": "行为原型",
                "marginal": "边际随机", "uniform": "均匀随机",
                "belief off": "信念关", "belief on": "信念开",
                "control": "冲击对照", "rumor": "冲击注入"}
    df_zh = df.rename(columns={**zh_label})
    df_zh["group"] = df_zh["group"].map(zh_group)
    df_zh = df_zh.rename(columns={"group": "实验组"})
    df_zh = df_zh[["实验组"] + [zh_label[a] for a in ACTIONS]]
    df_zh.to_csv(TBL / "table6_action_mix.csv", index=False)


# ----------------------------------------------------------------------
# Table 7 — B1 ten markets summary
# ----------------------------------------------------------------------

def table_b1_markets():
    import yaml
    yam = yaml.safe_load(
        (ROOT / "experiments/configs/b1_markets.yaml").read_text())
    markets = yam.get("markets", yam) if isinstance(yam, dict) else yam
    rows = []
    for m in markets:
        slug = m["slug"]
        ppath = ROOT / f"data/priors_{slug}.json"
        if not ppath.exists():
            continue
        pr = json.loads(ppath.read_text())
        from datetime import datetime
        suffix = datetime.utcfromtimestamp(int(pr["market_open_ts"])).strftime(
            "%Y%m%dT%H%M%SZ")
        wf_path = ROOT / f"data/clustering/wallet_features_{suffix}.parquet"
        cl_path = ROOT / f"data/clustering/wallet_clusters_{suffix}.parquet"
        sm_path = ROOT / f"data/clustering/clustering_summary_{suffix}.json"
        K, npre = None, None
        if sm_path.exists():
            sm = json.loads(sm_path.read_text())
            K = sm.get("chosen_K") or sm.get("K")
        for cand in (wf_path, cl_path):
            if npre is None and cand.exists():
                try:
                    npre = int(pd.read_parquet(cand, columns=None).shape[0])
                except Exception:
                    pass
        rows.append({
            "市场 slug": slug,
            "结算结果": "是" if m.get("winning_idx") == 0 else "否",
            "开盘日期": datetime.utcfromtimestamp(int(pr["market_open_ts"])).strftime("%Y-%m-%d"),
            "群体先验 P(是)": f"{pr['signal_mu']:.3f}",
            "仿真轮数": pr["n_ticks"],
            "最小报价": f"{pr['tick_size']:.3f}",
            "事件前钱包数": npre if npre is not None else "—",
            "聚类簇数": K if K is not None else "—",
        })
    pd.DataFrame(rows).to_csv(TBL / "table7_b1_markets.csv", index=False)


# ----------------------------------------------------------------------
# Table 8 — B3 archetype P&L stats
# ----------------------------------------------------------------------

def table_b3_archetype_pnl():
    frames = [_positions_pnl("b3", f"b3_archetype_s{s}").assign(seed=s)
              for s in (0, 1, 2)]
    df = pd.concat(frames, ignore_index=True)
    g = df.groupby("persona_type")["pnl"].agg(
        n="count", mean="mean", std="std", median="median",
        min="min", max="max").reset_index()
    g.columns = ["原型", "智能体数", "盈亏均值", "盈亏标准差",
                 "盈亏中位", "盈亏最小", "盈亏最大"]
    g = g.round(2)
    g.to_csv(TBL / "table8_b3_archetype_pnl.csv", index=False)


def main():
    fig_archetype_radar()
    fig_network_b6()
    fig_b1_normalized()
    fig_b4_pnl_kde()
    fig_action_mix_groups()
    table_b1_markets()
    table_b3_archetype_pnl()
    print("figures + tables written to docs/v13/figures/ and docs/v13/tables/")


if __name__ == "__main__":
    main()
