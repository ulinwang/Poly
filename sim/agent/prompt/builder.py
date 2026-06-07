"""Prompt assembly: load templates → render with persona + state.

Templates live in `agent/personas/templates/` so they can be diffed
across experiments. v8: Jinja2 for the system prompt that has
conditional blocks; the simpler base template uses plain `.format`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from agent.personas.persona import Persona
from agent.decision.types import AgentSnapshot, MarketSnapshot

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "personas" / "templates"


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=("txt", "j2")),
        keep_trailing_newline=True,
    )


def build_simple_system_prompt(
    persona: Persona, question: str, description: str, end_date: str,
) -> str:
    """Legacy single-side prompt (kept for backwards compat with v2/v3
    agents). Renders `templates/system_base.txt` via str.format."""
    text = (_TEMPLATE_DIR / "system_base.txt").read_text()
    desc = (description or "").strip()
    if len(desc) > 1500:
        desc = desc[:1500] + " ...[truncated]"
    return text.format(
        profile=persona.profile_text,
        risk_aversion=persona.risk_aversion,
        question=question,
        description=desc,
        end_date=end_date,
    )


def build_clob_system_prompt(
    persona: Persona, question: str, description: str, end_date: str,
    *, tick_size: float = 0.01, prompt_language: str = "en",
    info_enabled: bool = True, forum_enabled: bool = True,
) -> str:
    """v7 production prompt — both YES and NO books visible, supports
    LIMIT/MARKET/CANCEL/HOLD/SPLIT/MERGE actions.

    `info_enabled` / `forum_enabled` control whether the web-search and
    forum/social tools are described in the prompt, so the model is actually
    told it can gather context and participate socially (not just trade)."""
    desc = (description or "").strip()
    if len(desc) > 1200:
        desc = desc[:1200] + " ...[truncated]"
    risk_line = ""
    if persona.persona_type != "Calibrated":
        risk_line = (
            f"Risk aversion: {persona.risk_aversion} "
            f"(0 = loves risk, 1 = very averse)."
        )
    template_name = "clob_system_zh.j2" if prompt_language == "zh" else "clob_system.j2"
    tmpl = _env().get_template(template_name)
    return tmpl.render(
        profile=persona.profile_text,
        risk_aversion_line=risk_line,
        question=question,
        description=desc,
        end_date=end_date,
        tick_size=tick_size,
        info_enabled=info_enabled,
        forum_enabled=forum_enabled,
    )


def build_user_prompt(
    market: MarketSnapshot, agent: AgentSnapshot, *, prompt_language: str = "en",
    forum_enabled: bool = True,
) -> str:
    """Render `templates/user_state.j2` with the current market +
    agent snapshot.

    `forum_enabled` gates the social/forum section so it (and its
    "call read_forum…" prompt) appears even when the agent has no social
    memory yet — otherwise a fresh agent is never told the forum exists."""
    def _f(v: float | None) -> str:
        return f"{v:.3f}" if v is not None else "—"

    hist = market.yes_mid_history[-3:]
    empty_word = "(空)" if prompt_language == "zh" else "(empty)"
    none_word = "(无)" if prompt_language == "zh" else "(none)"
    hist_str = ", ".join(f"{p:.3f}" for p in hist) if hist else none_word

    def _fmt_depth(levels: list[dict] | None) -> str:
        if not levels:
            return empty_word
        return ", ".join(
            f"{float(x['price']):.3f}/${float(x['size']):.0f}"
            for x in levels[:5]
        )

    def _fmt_imbalance(v: float | None) -> str:
        return "无" if v is None and prompt_language == "zh" else (
            "n/a" if v is None else f"{v:+.2f}"
        )

    def _fmt_fills(rows: list[dict] | None) -> list[str]:
        out = []
        for r in (rows or [])[-5:]:
            if prompt_language == "zh":
                out.append(
                    "tick {tick}: {outcome} {maker_side} 挂单方 @ {price:.3f}, "
                    "{size:.2f} 份, ${notional:.2f}".format(**r)
                )
            else:
                out.append(
                    "tick {tick}: {outcome} {maker_side} maker @ {price:.3f}, "
                    "{size:.2f} shares, ${notional:.2f}".format(**r)
                )
        return out

    def _fmt_resting(rows: list[dict] | None) -> list[str]:
        out = []
        for r in (rows or [])[:10]:
            if prompt_language == "zh":
                out.append(
                    "{outcome}/{side} @{price:.3f}, 剩余 {remaining:.2f}, "
                    "已挂 {age_ticks} ticks".format(**r)
                )
            else:
                out.append(
                    "{outcome}/{side} @{price:.3f}, remaining {remaining:.2f}, "
                    "age {age_ticks} ticks".format(**r)
                )
        return out

    def _fmt_own_fills(rows: list[dict] | None) -> list[str]:
        out = []
        for r in (rows or [])[-5:]:
            if prompt_language == "zh":
                out.append(
                    "tick {tick}: {role} 在 {outcome} @ {price:.3f}, "
                    "{size:.2f} 份, ${notional:.2f}".format(**r)
                )
            else:
                out.append(
                    "tick {tick}: {role} on {outcome} @ {price:.3f}, "
                    "{size:.2f} shares, ${notional:.2f}".format(**r)
                )
        return out

    signal_block = ""
    if agent.private_signal_mu is not None:
        sigma = agent.private_signal_sigma if agent.private_signal_sigma is not None else 0.2
        if prompt_language == "zh":
            signal_block = (
                f"你在模拟开始时对 P(YES) 的私人先验估计为 "
                f"{agent.private_signal_mu:.2f}（1σ ≈ {sigma:.2f}）。"
                f"随着市场变化更新它；这是你的初始信念，不是真实结果。"
            )
        else:
            signal_block = (
                f"Your private prior estimate of P(YES) at sim start was "
                f"{agent.private_signal_mu:.2f} (1σ ≈ {sigma:.2f}). "
                f"Update it as the market evolves; it is your starting belief, not ground truth."
            )

    # v13 (AGT-4): surface the agent's explicit belief (if it has set
    # one via update_belief). `ticks_ago` is derived from the current
    # tick (= total_ticks - ticks_remaining) and the set_at_tick.
    belief = getattr(agent, "belief_snapshot", None) or None
    if belief is not None:
        current_tick = max(0, market.total_ticks - market.ticks_remaining)
        ticks_ago = max(0, current_tick - int(belief.get("set_at_tick", 0)))
    else:
        ticks_ago = 0

    # v15 (FORUM): build a bounded, priority-ordered "social memory" block.
    # Priority: posts by followed authors (the diffusion channel) are shown
    # first, then the agent's own recent posts, then who it follows. Content
    # is clipped per-line and the lists are already capped by the observer
    # (depth-limited) to keep the prompt from exploding.
    def _clip(text: str, n: int = 160) -> str:
        text = (text or "").strip().replace("\n", " ")
        return text if len(text) <= n else text[: n - 1] + "…"

    read_posts = getattr(agent, "social_read_posts", None) or []
    # followed-author posts first, then the rest (stable, preserves the
    # newest-first order the observer already applied within each band).
    followed_reads = [r for r in read_posts if r.get("followed")]
    other_reads = [r for r in read_posts if not r.get("followed")]
    social_read_lines = [
        ("[followed] " if r.get("followed") else "")
        + f"post #{r.get('post_id')} by agent {r.get('author_id')} "
        f"(tick {r.get('tick')}): {_clip(r.get('content', ''))}"
        for r in (followed_reads + other_reads)
    ]
    my_posts = getattr(agent, "social_my_posts", None) or []
    social_my_post_lines = [
        f"post #{p.get('post_id')} (tick {p.get('tick')}): "
        f"{_clip(p.get('content', ''))}"
        for p in my_posts
    ]
    social_following = getattr(agent, "social_following", None) or []

    template_name = "user_state_zh.j2" if prompt_language == "zh" else "user_state.j2"
    tmpl = _env().get_template(template_name)
    return tmpl.render(
        signal_block=signal_block,
        yes_bid=_f(market.yes_best_bid), yes_ask=_f(market.yes_best_ask),
        yes_mid=market.yes_mid,
        no_bid=_f(market.no_best_bid), no_ask=_f(market.no_best_ask),
        no_mid=market.no_mid,
        hist_str=hist_str,
        yes_bid_depth=_fmt_depth(market.yes_bid_depth),
        yes_ask_depth=_fmt_depth(market.yes_ask_depth),
        no_bid_depth=_fmt_depth(market.no_bid_depth),
        no_ask_depth=_fmt_depth(market.no_ask_depth),
        yes_order_imbalance=_fmt_imbalance(market.yes_order_imbalance),
        no_order_imbalance=_fmt_imbalance(market.no_order_imbalance),
        recent_fills=_fmt_fills(market.recent_fills),
        time_remaining_pct=market.time_remaining_pct,
        cash=agent.cash,
        yes_shares=agent.yes_shares, no_shares=agent.no_shares,
        n_resting_orders=agent.n_resting_orders,
        resting_orders=_fmt_resting(agent.resting_orders),
        recent_own_fills=_fmt_own_fills(agent.recent_own_fills),
        recent_decisions=getattr(agent, "recent_decisions", None) or [],
        belief_snapshot=belief,
        ticks_ago=ticks_ago,
        social_read_lines=social_read_lines,
        social_my_post_lines=social_my_post_lines,
        social_following=social_following,
        forum_enabled=forum_enabled,
    )
