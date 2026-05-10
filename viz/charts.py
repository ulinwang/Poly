"""Plotly chart builders. Each returns a self-contained HTML <div>.

These render against the SAME parquet schemas the runner writes
(see `experiments/parquet_sink.py:ACTION_COLUMNS` etc.). No SQL,
no live data — pure post-hoc visualization.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _to_div(fig: go.Figure) -> str:
    """Self-contained <div>. plotly.js loaded once at the page top."""
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={"displaylogo": False, "displayModeBar": False},
    )


def yes_mid_trajectory(actions_df: pd.DataFrame) -> str:
    """Per-tick YES mid (post-action). Falls back to (0, 0.5) if empty."""
    if actions_df.empty or "yes_mid_after" not in actions_df.columns:
        fig = go.Figure().update_layout(
            title="YES mid trajectory (no data)",
            xaxis_title="tick", yaxis_title="YES mid",
        )
        return _to_div(fig)

    by_tick = (
        actions_df.groupby("tick_idx")["yes_mid_after"]
        .last().reset_index().sort_values("tick_idx")
    )
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=by_tick["tick_idx"], y=by_tick["yes_mid_after"],
        mode="lines+markers", name="YES mid",
        line=dict(color="#1f77b4", width=2),
    ))
    fig.update_layout(
        title="YES mid trajectory",
        xaxis_title="tick", yaxis_title="YES mid",
        yaxis=dict(range=[0, 1]),
        margin=dict(l=40, r=20, t=40, b=40), height=320,
    )
    return _to_div(fig)


def per_agent_pnl(
    positions_df: pd.DataFrame, personas_df: pd.DataFrame,
    market_resolved_yes: Optional[int],
) -> str:
    """Final PnL per agent, sorted descending. Mark-to-resolution (settle)."""
    if positions_df.empty:
        return _to_div(go.Figure().update_layout(title="PnL per agent (no data)"))

    final_tick = positions_df["tick_idx"].max()
    last = positions_df[positions_df["tick_idx"] == final_tick].copy()

    if market_resolved_yes is not None:
        yes_payoff = 1.0 if market_resolved_yes == 1 else 0.0
        no_payoff = 1.0 - yes_payoff
        last["final_value"] = (
            last["cash"]
            + last["yes_shares"] * yes_payoff
            + last["no_shares"] * no_payoff
        )
    else:
        last["final_value"] = last["cash"]

    if not personas_df.empty and "capital_initial" in personas_df.columns:
        cap_lookup = dict(zip(
            personas_df["agent_id"], personas_df["capital_initial"],
        ))
        last["capital_initial"] = last["agent_id"].map(cap_lookup).fillna(0.0)
    else:
        last["capital_initial"] = 0.0

    last["pnl"] = last["final_value"] - last["capital_initial"]
    last = last.sort_values("pnl", ascending=False)

    fig = go.Figure(go.Bar(
        x=last["agent_id"].astype(str), y=last["pnl"],
        marker_color=["#22aa88" if v >= 0 else "#cc4422" for v in last["pnl"]],
        text=[f"${v:+.0f}" for v in last["pnl"]], textposition="outside",
    ))
    fig.update_layout(
        title=f"Final PnL per agent (resolved YES={market_resolved_yes})",
        xaxis_title="agent_id", yaxis_title="PnL ($)",
        margin=dict(l=40, r=20, t=40, b=40), height=320,
    )
    return _to_div(fig)


def action_mix_per_tick(actions_df: pd.DataFrame) -> str:
    """Stacked bar of action_type per tick."""
    if actions_df.empty:
        return _to_div(go.Figure().update_layout(title="Action mix (no data)"))
    agg = (
        actions_df.groupby(["tick_idx", "action_type"]).size()
        .unstack(fill_value=0).reindex(
            columns=["LIMIT", "MARKET", "CANCEL", "SPLIT", "MERGE", "HOLD"],
            fill_value=0,
        )
    )
    colors = {
        "LIMIT": "#22aa88", "MARKET": "#aa4422",
        "CANCEL": "#aa8822", "SPLIT": "#1144aa",
        "MERGE": "#aa1144", "HOLD": "#888888",
    }
    fig = go.Figure()
    for col in agg.columns:
        fig.add_trace(go.Bar(
            x=agg.index, y=agg[col], name=col,
            marker_color=colors.get(col, "#888"),
        ))
    fig.update_layout(
        title="Action mix per tick",
        xaxis_title="tick", yaxis_title="# actions",
        barmode="stack",
        margin=dict(l=40, r=20, t=40, b=40), height=320,
    )
    return _to_div(fig)
