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
    *, tick_size: float = 0.01,
) -> str:
    """v7 production prompt — both YES and NO books visible, supports
    LIMIT/MARKET/CANCEL/HOLD/SPLIT/MERGE actions."""
    desc = (description or "").strip()
    if len(desc) > 1200:
        desc = desc[:1200] + " ...[truncated]"
    risk_line = ""
    if persona.persona_type != "Calibrated":
        risk_line = (
            f"Risk aversion: {persona.risk_aversion} "
            f"(0 = loves risk, 1 = very averse)."
        )
    tmpl = _env().get_template("clob_system.j2")
    return tmpl.render(
        profile=persona.profile_text,
        risk_aversion_line=risk_line,
        question=question,
        description=desc,
        end_date=end_date,
        tick_size=tick_size,
    )


def build_user_prompt(
    market: MarketSnapshot, agent: AgentSnapshot,
) -> str:
    """Render `templates/user_state.j2` with the current market +
    agent snapshot."""
    def _f(v: float | None) -> str:
        return f"{v:.3f}" if v is not None else "—"

    hist = market.yes_mid_history[-3:]
    hist_str = ", ".join(f"{p:.3f}" for p in hist) if hist else "(none)"

    signal_block = ""
    if agent.private_signal_mu is not None:
        sigma = agent.private_signal_sigma if agent.private_signal_sigma is not None else 0.2
        signal_block = (
            f"Your private prior estimate of P(YES) at sim start was "
            f"{agent.private_signal_mu:.2f} (1σ ≈ {sigma:.2f}). "
            f"Update it as the market evolves; it is your starting belief, not ground truth."
        )

    tmpl = _env().get_template("user_state.j2")
    return tmpl.render(
        signal_block=signal_block,
        yes_bid=_f(market.yes_best_bid), yes_ask=_f(market.yes_best_ask),
        yes_mid=market.yes_mid,
        no_bid=_f(market.no_best_bid), no_ask=_f(market.no_best_ask),
        no_mid=market.no_mid,
        hist_str=hist_str,
        time_remaining_pct=market.time_remaining_pct,
        cash=agent.cash,
        yes_shares=agent.yes_shares, no_shares=agent.no_shares,
        n_resting_orders=agent.n_resting_orders,
        recent_decisions=getattr(agent, "recent_decisions", None) or [],
    )
