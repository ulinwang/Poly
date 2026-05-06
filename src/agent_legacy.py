"""
Agent simulation: ask an LLM (DeepSeek by default) to predict the YES
probability of each Polymarket market, store predictions in ClickHouse
for later evaluation against market prices and resolution outcomes.

Research design notes
---------------------
- The agent is *not* shown the market's current `outcome_prices`. We
  want an independent estimate so we can later measure agent accuracy
  vs the crowd-sourced market price.
- The market's `outcome_prices[0]` *at the time of prediction* is
  snapshotted into `agent_predictions.market_yes_price_at_prediction`
  for later regret/calibration analysis — but the agent never sees it.
- For closed markets the resolved YES outcome is also snapshotted so
  prediction accuracy can be evaluated immediately.
- Prompts are versioned (`PROMPT_VERSION`) so we can iterate the prompt
  and compare versions side-by-side without losing history.

Usage
-----
    uv run python -m src.agent --limit 50 --closed-only
    uv run python -m src.agent --limit 10 --dry-run    # don't call API
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Optional, Sequence

from .clickhouse_client import ClickHouse
from .config import get_settings


PROMPT_VERSION = "v1"
log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an expert forecaster evaluating prediction-market questions.

For each question you receive, output ONLY a JSON object with this exact schema:
{
  "yes_probability": <float between 0 and 1>,
  "confidence": "<low|medium|high>",
  "reasoning": "<one to three sentences explaining the key drivers>"
}

Rules:
- Output strictly the JSON object — no prose, no markdown fences.
- yes_probability is your point estimate that the market resolves YES.
- Be calibrated: extreme probabilities (0.99 / 0.01) require strong evidence.
- If the question is ambiguous or you lack information, say "low" confidence
  and pick a probability that reflects your uncertainty (often near 0.5).
- Do not be anchored by any prior or external odds; reason from first
  principles based on the question and any context provided.
"""


def build_user_prompt(
    question: str,
    description: str,
    outcomes: Sequence[str],
    end_date: Optional[dt.datetime],
) -> str:
    desc = (description or "").strip()
    if len(desc) > 2000:
        desc = desc[:2000] + " ...[truncated]"
    end_str = end_date.isoformat() if end_date else "unknown"
    outcomes_str = ", ".join(outcomes) if outcomes else "Yes, No"
    return (
        f"Question: {question}\n"
        f"Resolution date: {end_str}\n"
        f"Outcomes: {outcomes_str}\n"
        f"Resolution rules / context:\n{desc}\n"
    )


def parse_response(text: str) -> dict:
    """Extract the JSON object the model returned. Tolerant of stray
    prose or markdown fences around it."""
    text = text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        # remove first fence line
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -3]
        # strip optional language tag like "```json\n"
        text = text.strip()
    # Find first { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in response: {text[:200]!r}")
    obj = json.loads(text[start : end + 1])

    yp = obj.get("yes_probability")
    if not isinstance(yp, (int, float)):
        raise ValueError(f"yes_probability missing or not numeric: {obj!r}")
    yp = float(yp)
    if not (0.0 <= yp <= 1.0):
        raise ValueError(f"yes_probability {yp} outside [0,1]")
    return {
        "yes_probability": yp,
        "confidence": str(obj.get("confidence", "")).lower() or "unknown",
        "reasoning": str(obj.get("reasoning", "")).strip(),
    }


def call_deepseek(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    timeout: float = 60.0,
) -> dict:
    """Send one chat-completion request. Returns dict with keys:
    text, prompt_tokens, completion_tokens, raw."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    choice = obj["choices"][0]
    return {
        "text": choice["message"]["content"],
        "prompt_tokens": int(obj.get("usage", {}).get("prompt_tokens", 0)),
        "completion_tokens": int(obj.get("usage", {}).get("completion_tokens", 0)),
        "raw": raw,
    }


def _prediction_id(market_id: str, model: str, prompt_version: str, when: dt.datetime) -> str:
    h = hashlib.sha1(f"{market_id}|{model}|{prompt_version}|{when.isoformat()}".encode()).hexdigest()
    return h[:16]


def _yes_price(outcome_prices: Sequence) -> float:
    try:
        return float(outcome_prices[0]) if outcome_prices else 0.0
    except (TypeError, ValueError, IndexError):
        return 0.0


def _resolved_yes(outcome_prices: Sequence, closed: int) -> Optional[int]:
    if not closed:
        return None
    try:
        yes = float(outcome_prices[0])
        no = float(outcome_prices[1]) if len(outcome_prices) > 1 else 1.0 - yes
    except (TypeError, ValueError, IndexError):
        return None
    if yes >= 0.99 and no <= 0.01:
        return 1
    if no >= 0.99 and yes <= 0.01:
        return 0
    return None  # partial / unresolved scaling


def predict_one(
    *,
    market_row: tuple,
    api_key: str,
    base_url: str,
    model: str,
    prompt_version: str = PROMPT_VERSION,
    temperature: float = 0.0,
    timeout: float = 60.0,
    call_fn=call_deepseek,
    now_fn=dt.datetime.utcnow,
) -> tuple:
    """Make one prediction. Returns the row tuple ready to insert into
    `agent_predictions`. Captures errors as rows with empty
    yes_probability and api_error set, so the run keeps moving."""
    (market_id, slug, question, description, outcomes,
     outcome_prices, volume, end_date, closed) = market_row

    user_prompt = build_user_prompt(question, description, outcomes, end_date)
    started = time.time()
    predicted_at = now_fn()
    api_error = ""
    raw = ""
    parsed = {"yes_probability": 0.0, "confidence": "", "reasoning": ""}
    prompt_tokens = 0
    completion_tokens = 0

    try:
        result = call_fn(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=temperature,
            timeout=timeout,
        )
        raw = result["raw"]
        prompt_tokens = result["prompt_tokens"]
        completion_tokens = result["completion_tokens"]
        parsed = parse_response(result["text"])
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        api_error = f"http: {exc}"
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        api_error = f"parse: {exc}"

    latency_ms = int((time.time() - started) * 1000)
    pid = _prediction_id(market_id, model, prompt_version, predicted_at)
    return (
        pid,
        market_id,
        model,
        prompt_version,
        float(parsed["yes_probability"]),
        parsed["confidence"],
        parsed["reasoning"],
        raw,
        prompt_tokens,
        completion_tokens,
        _yes_price(outcome_prices),
        _resolved_yes(outcome_prices, closed),
        float(volume or 0.0),
        latency_ms,
        api_error,
        predicted_at,
    )


def run(
    limit: int = 20,
    only_closed: bool = True,
    min_volume: float = 1000.0,
    dry_run: bool = False,
    insert_batch: int = 20,
    skip_already_predicted: bool = True,
    ch: Optional[ClickHouse] = None,
) -> int:
    settings = get_settings()
    if not settings.DEEPSEEK_API_KEY and not dry_run:
        raise SystemExit(
            "POLYMETL_DEEPSEEK_API_KEY is required (set it in .env). "
            "Use --dry-run to preview without calling the API."
        )

    if ch is None:
        ch = ClickHouse(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )
    ch.ensure_predictions_schema()

    rows = ch.fetch_markets_for_prediction(
        limit=limit,
        only_closed=only_closed,
        min_volume=min_volume,
        skip_predicted_by_model=settings.DEEPSEEK_MODEL if skip_already_predicted else None,
        skip_predicted_by_prompt=PROMPT_VERSION if skip_already_predicted else None,
    )
    log.info("selected %s markets to predict (only_closed=%s, min_volume=%s)",
             len(rows), only_closed, min_volume)
    if not rows:
        return 0

    if dry_run:
        for i, r in enumerate(rows[:5], 1):
            log.info("[dry-run] #%s %s — %s", i, r[1], r[2][:80])
        log.info("[dry-run] would have called %s for %s markets",
                 settings.DEEPSEEK_MODEL, len(rows))
        return 0

    buffer: list[tuple] = []
    completed = 0
    for i, market_row in enumerate(rows, 1):
        out_row = predict_one(
            market_row=market_row,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            model=settings.DEEPSEEK_MODEL,
            temperature=settings.DEEPSEEK_TEMPERATURE,
            timeout=settings.DEEPSEEK_TIMEOUT,
        )
        buffer.append(out_row)
        completed += 1
        err = out_row[14]
        log.info(
            "[%s/%s] %s yes_p=%.3f conf=%s lat=%sms %s",
            i, len(rows), market_row[1], out_row[4], out_row[5],
            out_row[13], (f"err={err}" if err else "ok"),
        )
        if len(buffer) >= insert_batch:
            ch.insert_predictions(buffer)
            buffer = []
    if buffer:
        ch.insert_predictions(buffer)
    log.info("done; predictions made: %s", completed)
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM agent simulator for Polymarket markets"
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--include-active",
        action="store_true",
        help="include active markets (default: only resolved markets)",
    )
    parser.add_argument(
        "--min-volume", type=float, default=1000.0,
        help="skip markets with lifetime volume below this (USD)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="select markets and build prompts but do not call the API",
    )
    parser.add_argument(
        "--no-skip", action="store_true",
        help="re-predict markets already predicted by this model+prompt",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run(
        limit=args.limit,
        only_closed=not args.include_active,
        min_volume=args.min_volume,
        dry_run=args.dry_run,
        skip_already_predicted=not args.no_skip,
    )


if __name__ == "__main__":
    main()
