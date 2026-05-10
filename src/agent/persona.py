"""
Persona dataclass + system-prompt template for the multi-agent
Polymarket simulator.

The v2/v3 hardcoded archetypes (SkepticalEngineer, LotteryPlayer,
HerdFollower, MarketMaker) were dropped in v7. Calibrated agents
(`persona_type = "Calibrated"`) get their `profile_text` from
`src.population.persona_generator`, which renders one paragraph per
real Polymarket wallet from observed trade history + `dataapi_holders`
bio + display_name. No role labels are baked in; roles emerge from
interaction structure (paper §3.4) and are recovered post-hoc by
`src.analysis.serd`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    persona_type: str
    risk_aversion: float
    capital_initial: float
    profile_text: str


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
