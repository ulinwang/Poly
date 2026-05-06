"""
Per-tick LLM decision in a CLOB market.

Action schema (JSON only):

  {
    "order_type": "LIMIT" | "MARKET" | "CANCEL" | "HOLD",
    "outcome":    "YES"   | "NO",       // which token's book to act on
    "side":       "BUY"   | "SELL",     // direction within that book
    "price":      <float in [0,1]>,     // required for LIMIT
    "size_usd":   <float>,              // notional intent in USDC
    "reasoning":  "<one to two sentences>"
  }

LIMIT  - rest on the book at price; may match if it crosses the spread
MARKET - sweep best opposite side until size_usd is consumed
CANCEL - cancel ALL of this agent's resting orders on (outcome, side)
HOLD   - no-op (size_usd = 0)
"""
from __future__ import annotations

import json
import time
import urllib.error
from dataclasses import dataclass

from ..agent_legacy import call_deepseek
from .personas import Persona, build_system_prompt


@dataclass
class MarketSnapshot:
    yes_best_bid: float | None
    yes_best_ask: float | None
    yes_mid: float
    no_best_bid: float | None
    no_best_ask: float | None
    no_mid: float
    yes_mid_history: list[float]   # last few ticks, oldest first
    ticks_remaining: int
    total_ticks: int

    @property
    def time_remaining_pct(self) -> float:
        return self.ticks_remaining / max(self.total_ticks, 1)


@dataclass
class AgentSnapshot:
    agent_id: int
    cash: float
    yes_shares: float
    no_shares: float
    n_resting_orders: int
    # v4: optional empirical private signal. None = legacy v2/v3 path.
    private_signal_mu: float | None = None
    private_signal_sigma: float | None = None


@dataclass
class Decision:
    order_type: str          # LIMIT | MARKET | CANCEL | HOLD
    outcome: str             # YES | NO
    side: str                # BUY | SELL
    price: float             # 0..1, only meaningful for LIMIT
    size_usd: float
    reasoning: str
    raw_response: str
    api_latency_ms: int
    api_error: str


VALID_ORDER_TYPES = {"LIMIT", "MARKET", "CANCEL", "HOLD", "SPLIT", "MERGE"}
VALID_OUTCOMES = {"YES", "NO"}
VALID_SIDES = {"BUY", "SELL"}


def round_to_tick(price: float, tick_size: float = 0.01) -> float:
    """Snap a price to the nearest tick. Polymarket default tick is 0.01."""
    if tick_size <= 0:
        return price
    return round(price / tick_size) * tick_size


def build_user_prompt(market: MarketSnapshot, agent: AgentSnapshot) -> str:
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
            f"Update it as the market evolves; it is your starting belief, not ground truth.\n\n"
        )
    return (
        signal_block
        + f"Order books right now:\n"
        f"  YES book — bid {_f(market.yes_best_bid)}, ask {_f(market.yes_best_ask)}, mid {market.yes_mid:.3f}\n"
        f"  NO book  — bid {_f(market.no_best_bid)}, ask {_f(market.no_best_ask)}, mid {market.no_mid:.3f}\n"
        f"  YES mid history (last 3 ticks): {hist_str}\n"
        f"  Time remaining: {market.time_remaining_pct:.0%} of market lifetime\n"
        f"\n"
        f"Your portfolio:\n"
        f"  Cash: ${agent.cash:.2f}\n"
        f"  YES shares: {agent.yes_shares:.2f}\n"
        f"  NO shares:  {agent.no_shares:.2f}\n"
        f"  Resting orders open: {agent.n_resting_orders}\n"
        f"\n"
        f"What is your action this tick? Reply with the JSON action object."
    )


CLOB_SYSTEM_PROMPT_TEMPLATE = """You are a Polymarket prediction-market trader. Trading style:

{profile}
{risk_aversion_line}
Market question: "{question}"
Resolution rules: {description}
Resolution date: {end_date}

Each tick you observe both order books (YES outcome and NO outcome) and decide ONE action. Output ONLY this JSON, no prose, no fences:

{{
  "order_type": "LIMIT" | "MARKET" | "CANCEL" | "HOLD",
  "outcome": "YES" | "NO",
  "side": "BUY" | "SELL",
  "price": <number in [0,1], required only for LIMIT>,
  "size_usd": <number>,
  "reasoning": "<one to two sentences in your persona's voice>"
}}

Rules:
- LIMIT places a resting order at `price`; matches if it crosses, else rests.
- MARKET sweeps the best opposite side immediately.
- CANCEL cancels ALL your resting orders on (outcome, side).
- HOLD: no-op; size_usd = 0.
- SPLIT mints a 1:1 pair: spend `size_usd` USD to receive `size_usd` YES shares AND `size_usd` NO shares simultaneously. Useful for market makers seeding two-sided inventory. `outcome`/`side`/`price` are ignored.
- MERGE redeems a pair: destroy `size_usd` matched YES+NO shares (capped by your inventory) to recover `size_usd` USD. `outcome`/`side`/`price` are ignored.
- size_usd must be ≤ your cash for BUY; for SELL, you must hold shares of that outcome.
- Polymarket enforces tick size 0.01 on prices; submit prices in 0.01 increments.
- Stay in character. Do not reveal the market's eventual resolution; you do not know it.
"""


def _build_clob_system_prompt(persona: Persona, question: str, description: str, end_date: str) -> str:
    desc = (description or "").strip()
    if len(desc) > 1200:
        desc = desc[:1200] + " ...[truncated]"
    # For v4 calibrated personas, the behavioral profile_text already
    # encodes everything we know about the trader; the abstract
    # risk_aversion scalar adds noise rather than signal. Suppress it.
    if persona.persona_type == "Calibrated":
        risk_line = ""
    else:
        risk_line = (
            f"\nRisk aversion: {persona.risk_aversion} "
            f"(0 = loves risk, 1 = very averse).\n"
        )
    return CLOB_SYSTEM_PROMPT_TEMPLATE.format(
        profile=persona.profile_text,
        risk_aversion_line=risk_line,
        question=question,
        description=desc,
        end_date=end_date,
    )


def parse_decision(text: str, tick_size: float = 0.01) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError(f"no JSON object: {text[:200]!r}")
    obj = json.loads(text[start : end + 1])

    order_type = str(obj.get("order_type", "")).upper()
    if order_type not in VALID_ORDER_TYPES:
        raise ValueError(f"invalid order_type: {order_type!r}")
    if order_type in {"SPLIT", "MERGE"}:
        # outcome/side/price are not meaningful for SPLIT/MERGE
        outcome = "YES"
        side = "BUY"
        price = 0.0
    else:
        outcome = str(obj.get("outcome", "YES")).upper()
        if outcome not in VALID_OUTCOMES:
            outcome = "YES"
        side = str(obj.get("side", "BUY")).upper()
        if side not in VALID_SIDES:
            side = "BUY"
        try:
            price = float(obj.get("price", 0.5))
        except (TypeError, ValueError):
            price = 0.5
        price = max(0.0, min(1.0, price))
        price = round_to_tick(price, tick_size=tick_size)
    try:
        size_usd = float(obj.get("size_usd", 0))
    except (TypeError, ValueError):
        size_usd = 0.0
    if size_usd < 0:
        size_usd = 0.0
    if order_type == "HOLD":
        size_usd = 0.0
    return {
        "order_type": order_type, "outcome": outcome, "side": side,
        "price": price, "size_usd": size_usd,
        "reasoning": str(obj.get("reasoning", "")).strip(),
    }


def decide(
    *,
    persona: Persona,
    question: str,
    description: str,
    end_date: str,
    market: MarketSnapshot,
    agent: AgentSnapshot,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float = 0.4,
    timeout: float = 120.0,
    call_fn=call_deepseek,
) -> Decision:
    system_prompt = _build_clob_system_prompt(persona, question, description, end_date)
    user_prompt = build_user_prompt(market, agent)

    started = time.time()
    raw = ""
    api_error = ""
    parsed = {
        "order_type": "HOLD", "outcome": "YES", "side": "BUY",
        "price": 0.5, "size_usd": 0.0, "reasoning": "",
    }
    try:
        result = call_fn(
            base_url=base_url, api_key=api_key, model=model,
            system_prompt=system_prompt, user_prompt=user_prompt,
            temperature=temperature, timeout=timeout,
            response_format={"type": "json_object"},
        )
        raw = result["raw"]
        parsed = parse_decision(result["text"])
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        api_error = f"http: {exc}"
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        api_error = f"parse: {exc}"

    latency_ms = int((time.time() - started) * 1000)
    return Decision(
        order_type=parsed["order_type"], outcome=parsed["outcome"],
        side=parsed["side"], price=parsed["price"],
        size_usd=parsed["size_usd"], reasoning=parsed["reasoning"],
        raw_response=raw, api_latency_ms=latency_ms, api_error=api_error,
    )
