"""Additional thesis figures + table CSVs from committed sim artifacts.

Outputs (all reproducible from on-disk parquets + cluster profiles):

  docs/v13/figures/
    fig8_archetype_radar.png    — 4-archetype centroid radar (7 features)
    fig9_network_b6.png         — B6 maker–taker network (control vs rumor)
    fig10_b1_normalized.png     — B1 ten markets' normalized price trajectories
    fig11_b4_pnl_kde.png        — B4 per-agent P&L distribution, on vs off
    fig12_action_mix_groups.png — full action-mix stacked bar across 8 groups

  docs/v13/tables/
    table6_action_mix.csv       — 8 treatment groups × 7 action types (%)
    table7_b1_markets.csv       — per-B1-market priors + cluster summary
    table8_b3_archetype_pnl.csv — per-cluster P&L stats in B3-archetype runs

Run:  uv run python scripts/thesis_extra_artifacts.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "docs" / "v13" / "figures"
TBL = ROOT / "docs" / "v13" / "tables"
FIG.mkdir(parents=True, exist_ok=True)
TBL.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Serif", "font.size": 10,
    "axes.edgecolor": "#222", "axes.linewidth": 0.8,
    "axes.grid": True, "grid.color": "#ddd", "grid.linewidth": 0.5,
    "figure.dpi": 150, "savefig.bbox": "tight",
})
DARK = "#1a1a1a"
GRAY = "#888"

ACTIONS = ["LIMIT", "MARKET", "CANCEL", "HOLD", "SPLIT", "MERGE", "UPDATE_BELIEF"]
ACTION_LABEL = {
    "LIMIT": "限价单", "MARKET": "市价单", "CANCEL": "撤单",
    "HOLD": "不操作", "SPLIT": "拆分", "MERGE": "合并",
    "UPDATE_BELIEF": "声明信念",
}
ACTION_COLOR = {
    "LIMIT": "#4a4a4a", "MARKET": "#7a7a7a", "CANCEL": "#a8a8a8",
    "HOLD": "#cdcdcd", "SPLIT": "#666", "MERGE": "#888",
    "UPDATE_BELIEF": "#2a2a2a",
}


def _eid(suite, name):
    idx = json.loads((ROOT / f"output_v13/{suite}/index.json").read_text())
    for r in idx["runs"]:
        if r["name"] == name:
            return r["exp_id"]
    raise KeyError(name)


def _acts(suite, name):
    return pd.read_parquet(
        ROOT / f"output_v13/{suite}/{_eid(suite, name)}/raw/agent_actions.parquet"
    )


def _fills(suite, name):
    return pd.read_parquet(
        ROOT / f"output_v13/{suite}/{_eid(suite, name)}/raw/agent_fills.parquet"
    )


def _positions_pnl(suite, name):
    eid = _eid(suite, name)
    per = pd.read_parquet(ROOT / f"output_v13/{suite}/{eid}/raw/agent_personas.parquet")
    pos = pd.read_parquet(ROOT / f"output_v13/{suite}/{eid}/raw/agent_positions.parquet")
    last = pos.sort_values("tick_idx").groupby("agent_id").last().reset_index()
    m = last.merge(per[["agent_id", "capital_initial", "persona_type"]], on="agent_id")
    m["pnl"] = m["cash"] + m["unrealized_pnl"] - m["capital_initial"]
    return m


# ----------------------------------------------------------------------
# 图 8: 四原型雷达图（K=4, 基底市场 cutoff）
# ----------------------------------------------------------------------

def fig_archetype_radar():
    p = ROOT / "data/clustering/cluster_profiles_20230523T153721Z.json"
    d = json.loads(p.read_text())
    feats = d["feat_cols"]
    # normalize each feature across clusters to [0,1] for visual comparison
    raw = np.array([[d["clusters"][str(k)]["centroid"][f] for f in feats]
                    for k in range(d["K"])])
    mn, mx = raw.min(axis=0), raw.max(axis=0)
    norm = (raw - mn) / np.where(mx - mn > 0, mx - mn, 1.0)
    feat_labels_zh = [
        "累计名义额\n(对数)", "市场集中度", "单位资金\n市场广度",
        "平均成交价", "尾部交易\n占比", "活跃时长\n(对数)", "成交价波动",
    ]
    angles = np.linspace(0, 2 * np.pi, len(feats), endpoint=False).tolist()
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=(6.2, 5.6),
                           subplot_kw=dict(polar=True))
    for k in range(d["K"]):
        v = norm[k].tolist() + [norm[k][0]]
        ax.plot(angles, v, lw=1.6, color=DARK, alpha=0.45 + 0.18 * k,
                marker="o", ms=3.5, label=f"原型 {k + 1}（{d['clusters'][str(k)]['pct']*100:.1f}%）")
        ax.fill(angles, v, color=DARK, alpha=0.05)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(feat_labels_zh, fontsize=8.5,
                       fontproperties=_zh_font())
    ax.set_yticklabels([])
    ax.set_rlabel_position(0)
    ax.legend(loc="upper right", bbox_to_anchor=(1.32, 1.05),
              frameon=False, fontsize=8.5, prop=_zh_font())
    fig.savefig(FIG / "fig8_archetype_radar.png"); plt.close(fig)


def _zh_font():
    """Try to find a CJK font on the system; fall back to default."""
    from matplotlib import font_manager
    for cand in ("PingFang SC", "Heiti TC", "STHeiti", "Arial Unicode MS",
                 "Songti SC", "SimHei"):
        try:
            font_manager.findfont(cand, fallback_to_default=False)
            return font_manager.FontProperties(family=cand)
        except Exception:
            continue
    return None


# ----------------------------------------------------------------------
# 图 9: B6 maker-taker network — control vs rumor
# ----------------------------------------------------------------------

def fig_network_b6():
    import sys
    sys.path.insert(0, str(ROOT))
    from experiments.analysis.network import build_network
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    for ax, name, title in [(axes[0], "b6_control_s0", "(a) 无冲击对照"),
                            (axes[1], "b6_rumor_s0", "(b) 注入传闻")]:
        f = _fills("b6", name)
        g = build_network(f, exclude_env_maker=True)
        if g.number_of_edges() == 0:
            ax.text(0.5, 0.5, "no flow", ha="center", va="center"); continue
        pos = nx.spring_layout(g, seed=0, k=1.5 / np.sqrt(max(1, g.number_of_nodes())))
        weights = np.array([d["weight"] for *_, d in g.edges(data=True)])
        wnorm = 0.5 + 3.0 * (weights / weights.max())
        node_size = [60 + 0.05 * g.degree(n, weight="weight") for n in g.nodes()]
        nx.draw_networkx_edges(g, pos, ax=ax, alpha=0.35,
                               width=wnorm, edge_color="#666",
                               arrows=True, arrowsize=6,
                               connectionstyle="arc3,rad=0.06")
        nx.draw_networkx_nodes(g, pos, ax=ax, node_size=node_size,
                               node_color="#bbb", edgecolors=DARK, linewidths=0.6)
        ax.set_title(title, fontsize=10, fontproperties=_zh_font())
        ax.axis("off")
    fig.savefig(FIG / "fig9_network_b6.png"); plt.close(fig)


# ----------------------------------------------------------------------
# 图 10: B1 ten markets normalized trajectories
# ----------------------------------------------------------------------

def fig_b1_normalized():
    idx = json.loads((ROOT / "output_v13/b1/index.json").read_text())
    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    for r in idx["runs"]:
        a = pd.read_parquet(
            ROOT / f"output_v13/b1/{r['exp_id']}/raw/agent_actions.parquet"
        ).sort_values("tick_idx")
        s = a.groupby("tick_idx")["yes_mid_after"].last()
        # normalize: subtract start so all curves originate at 0
        y = s.values - float(a["yes_mid_before"].iloc[0])
        x = np.arange(len(y)) / max(len(y) - 1, 1)
        ax.plot(x, y, color=DARK, alpha=0.55, lw=1.2, marker="o", ms=2)
    ax.axhline(0, color=GRAY, ls="--", lw=1)
    ax.set_xlabel("relative round (0 = start, 1 = settlement)")
    ax.set_ylabel("YES mid-price change vs start")
    ax.set_title("10 markets, each line one market", fontsize=9.5)
    fig.savefig(FIG / "fig10_b1_normalized.png"); plt.close(fig)


# ----------------------------------------------------------------------
# 图 11: B4 individual P&L distribution, belief on vs off (3 seeds each)
# ----------------------------------------------------------------------

def fig_b4_pnl_kde():
    off, on = [], []
    for s in (0, 1, 2):
        off += _positions_pnl("b4", f"b4_belief_off_s{s}")["pnl"].tolist()
        on += _positions_pnl("b4", f"b4_belief_on_s{s}")["pnl"].tolist()
    off = np.array(off); on = np.array(on)
    bins = np.linspace(min(off.min(), on.min()), max(off.max(), on.max()), 40)
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    ax.hist(off, bins=bins, color="#ccc", edgecolor=DARK,
            alpha=0.85, label=f"信念机制关 (n={len(off)})")
    ax.hist(on, bins=bins, edgecolor=DARK, lw=1.5,
            label=f"信念机制开 (n={len(on)})", histtype="step")
    ax.axvline(0, color=GRAY, ls="--", lw=1)
    ax.set_xlabel("individual agent P&L (USD)")
    ax.set_ylabel("count")
    ax.legend(frameon=False, fontsize=8.5, prop=_zh_font())
    fig.savefig(FIG / "fig11_b4_pnl_kde.png"); plt.close(fig)


# ----------------------------------------------------------------------
# 图 12 + 表 6: action mix across 8 treatment groups
# ----------------------------------------------------------------------

GROUPS = [
    ("基线", [("b2", f"b2_s{s}") for s in (0, 1, 2)]),
    ("行为原型", [("b3", f"b3_archetype_s{s}") for s in (0, 1, 2)]),
    ("边际随机", [("b3", f"b3_marginal_s{s}") for s in (0, 1, 2)]),
    ("均匀随机", [("b3", f"b3_uniform_s{s}") for s in (0, 1, 2)]),
    ("信念关", [("b4", f"b4_belief_off_s{s}") for s in (0, 1, 2)]),
    ("信念开", [("b4", f"b4_belief_on_s{s}") for s in (0, 1, 2)]),
    ("冲击对照", [("b6", f"b6_control_s{s}") for s in (0, 1, 2)]),
    ("冲击注入", [("b6", f"b6_rumor_s{s}") for s in (0, 1, 2)]),
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
    rows = []
    for label, runs in GROUPS:
        mix = _group_mix(runs)
        rows.append({"group": label, **mix})
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(8.2, 4.0))
    bottom = np.zeros(len(df))
    for a in ACTIONS:
        ax.bar(df["group"], df[a], bottom=bottom, label=ACTION_LABEL[a],
               color=ACTION_COLOR[a], edgecolor=DARK, linewidth=0.4)
        bottom += df[a].values
    ax.set_ylabel("share of all actions (%)")
    ax.set_ylim(0, 100)
    ax.legend(ncol=4, bbox_to_anchor=(0.5, -0.18), loc="upper center",
              frameon=False, fontsize=8.5, prop=_zh_font())
    for lbl in ax.get_xticklabels():
        lbl.set_fontproperties(_zh_font()); lbl.set_fontsize(9)
    fig.savefig(FIG / "fig12_action_mix_groups.png"); plt.close(fig)
    # CSV with one row per group
    out = df[["group"] + ACTIONS].copy()
    out.columns = ["实验组"] + [ACTION_LABEL[a] for a in ACTIONS]
    out.to_csv(TBL / "table6_action_mix.csv", index=False)
    return out


# ----------------------------------------------------------------------
# 表 7: B1 ten markets — per-market priors + clustering summary
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
        sm_path = ROOT / f"data/clustering/clustering_summary_{suffix}.json"
        wf_path = ROOT / f"data/clustering/wallet_features_{suffix}.parquet"
        K, sil, jacc, npre = None, None, None, None
        if sm_path.exists():
            sm = json.loads(sm_path.read_text())
            K = sm.get("chosen_K") or sm.get("K")
            for d in sm.get("per_K", []) + sm.get("sweep", []):
                if d.get("K") == K:
                    sil = d.get("silhouette"); jacc = d.get("median_jaccard")
            npre = sm.get("n_wallets") or sm.get("n_rows")
        if npre is None and wf_path.exists():
            try:
                npre = int(pd.read_parquet(wf_path, columns=["wallet"]).shape[0])
            except Exception:
                pass
        # alt: if the per-market features parquet is gitignored, fall back to
        # reading the clusters parquet which is committed for each cutoff.
        if npre is None:
            cl_path = ROOT / f"data/clustering/wallet_clusters_{suffix}.parquet"
            if cl_path.exists():
                try:
                    npre = int(pd.read_parquet(cl_path).shape[0])
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
    df = pd.DataFrame(rows)
    df.to_csv(TBL / "table7_b1_markets.csv", index=False)
    return df


# ----------------------------------------------------------------------
# 表 8: B3 archetype runs — per-cluster P&L stats
# ----------------------------------------------------------------------

def table_b3_archetype_pnl():
    frames = []
    for s in (0, 1, 2):
        frames.append(_positions_pnl("b3", f"b3_archetype_s{s}").assign(seed=s))
    df = pd.concat(frames, ignore_index=True)
    g = df.groupby("persona_type")["pnl"].agg(
        n="count", mean="mean", std="std", median="median",
        min="min", max="max").reset_index()
    g.columns = ["原型", "智能体数", "盈亏均值", "盈亏标准差",
                 "盈亏中位", "盈亏最小", "盈亏最大"]
    g = g.round(2)
    g.to_csv(TBL / "table8_b3_archetype_pnl.csv", index=False)
    return g


def main():
    fig_archetype_radar()
    fig_network_b6()
    fig_b1_normalized()
    fig_b4_pnl_kde()
    mix = fig_action_mix_groups()
    b1 = table_b1_markets()
    pnl = table_b3_archetype_pnl()
    print("figures →", FIG)
    for p in sorted(FIG.glob("fig*.png")):
        print(" ", p.name, p.stat().st_size, "bytes")
    print("tables →", TBL)
    for p in sorted(TBL.glob("table*.csv")):
        print(" ", p.name)


if __name__ == "__main__":
    main()
