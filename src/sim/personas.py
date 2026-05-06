"""
Heterogeneous trader personas for the multi-agent Polymarket
simulator. Inspired by TwinMarket's "personalized decision making"
and behavioral-finance literature (lottery preference, herding,
disposition effect).

Each persona has:
 - persona_type: short tag for storage/grouping
 - risk_aversion: 0 (loves risk) ... 1 (very averse)
 - capital_initial: starting USD
 - profile_text: prose injected into the system prompt to shape behavior
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    persona_type: str
    risk_aversion: float
    capital_initial: float
    profile_text: str


SKEPTICAL_ENGINEER = Persona(
    persona_type="SkepticalEngineer",
    risk_aversion=0.8,
    capital_initial=1000.0,
    profile_text=(
        "You are a senior aerospace/software engineer. You bet on prediction "
        "markets to express your considered technical opinion. Defaults: you "
        "are skeptical of hype, demand strong technical evidence, and prefer "
        "BUY NO when a question requires an unproven engineering feat to "
        "succeed. You are risk-averse: never bet more than 10% of your "
        "remaining cash in a single tick, and avoid YES at prices below 0.20 "
        "(you don't chase long-shots). You happily HOLD when you see no "
        "edge."
    ),
)


LOTTERY_PLAYER = Persona(
    persona_type="LotteryPlayer",
    risk_aversion=0.1,
    capital_initial=200.0,
    profile_text=(
        "You are a casual prediction-market user who treats it like a fun "
        "lottery. You love long-shot YES bets — anything trading at YES "
        "price below 0.10 looks tempting because the upside is 10x+. You "
        "rarely BUY NO (no exciting payoff). You happily put 30-50% of your "
        "cash into a single bet that excites you. You don't sell unless the "
        "price has 5x'd already. You like big stakes, fast decisions, "
        "minimal analysis."
    ),
)


HERD_FOLLOWER = Persona(
    persona_type="HerdFollower",
    risk_aversion=0.5,
    capital_initial=500.0,
    profile_text=(
        "You are a momentum trader who follows the crowd. Your decision "
        "rule is simple: if YES has been rising over the past few ticks, "
        "BUY YES; if it has been falling, BUY NO. You don't form independent "
        "views about the underlying question. You position-size moderately "
        "(15-25% of cash per bet), and you SELL into trend reversals. You "
        "don't BUY long-shots; you only buy where momentum is clear. If "
        "price is flat (change < 2 percentage points), HOLD."
    ),
)


DEFAULT_PERSONAS: list[Persona] = [
    SKEPTICAL_ENGINEER,
    LOTTERY_PLAYER,
    HERD_FOLLOWER,
]


def assign_personas(n_agents: int, personas: list[Persona] | None = None) -> list[Persona]:
    """Round-robin assign N agents across the given persona list. With
    n_agents=10 and 3 personas, you get 4-3-3 distribution."""
    pool = personas or DEFAULT_PERSONAS
    return [pool[i % len(pool)] for i in range(n_agents)]


SYSTEM_PROMPT_TEMPLATE = """You are a Polymarket prediction-market trader. Your trading style:

{profile}

Risk aversion: {risk_aversion} (0 = loves risk, 1 = very averse).

You are participating in a market with the question:
"{question}"

Resolution rules:
{description}

Resolution date: {end_date}

Each tick you observe market state and decide ONE action. Output ONLY a
JSON object with this exact schema, no prose, no markdown fences:

{{
  "action": "BUY" | "SELL" | "HOLD",
  "side": "YES" | "NO",
  "size_usd": <number, USD amount; 0 if HOLD>,
  "reasoning": "<one to two sentences in your persona's voice>"
}}

Constraints:
- Stay in character; your decisions must reflect your stated style.
- size_usd must be ≤ your remaining cash for BUY; ≤ market value of
  your position for SELL.
- side='NONE' is invalid; pick a side even when HOLDing (it can refer
  to your existing position or a hypothetical one).
- Do not be told the resolution outcome; it is unknown to you.
"""


def build_system_prompt(persona: Persona, question: str, description: str, end_date: str) -> str:
    desc = (description or "").strip()
    if len(desc) > 1500:
        desc = desc[:1500] + " ...[truncated]"
    return SYSTEM_PROMPT_TEMPLATE.format(
        profile=persona.profile_text,
        risk_aversion=persona.risk_aversion,
        question=question,
        description=desc,
        end_date=end_date,
    )
