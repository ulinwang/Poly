"""
v4 Phase 2 — Generate behavioral profile_text from each wallet's
pre-event features. Uses a one-shot DeepSeek call per wallet, cached
to disk so repeated sims do not re-pay for LLM calls.

Methodological constraint: the prompt EXPLICITLY forbids role-typing
words (no "market maker", "whale", "novice", "expert", "apex", "prey",
etc.). This preserves the SERD validation principle that roles must
emerge from the network, not from initialization labels.

Usage:
    uv run python -m src.sim.persona_generator \\
        --target-market-id 581883 [--force]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import os
from pathlib import Path
from typing import Optional

from ..agent_legacy import call_deepseek
from ..clickhouse_client import ClickHouse
from ..config import get_settings


CACHE_PATH = Path("data/wallet_personas.json")

# Words a profile must NOT contain. Verified post-generation.
FORBIDDEN_LABELS = (
    "market maker", "market-maker", "whale", "novice", "expert",
    "apex", "prey", "predator", "pro trader", "amateur", "shark",
    "sophisticated investor",
)
_FORBIDDEN_RE = re.compile("|".join(re.escape(w) for w in FORBIDDEN_LABELS), re.IGNORECASE)


SYSTEM_PROMPT = (
    "You write concise behavioral profiles for a market simulation. "
    "Rules: (1) Output only the profile paragraph in second person "
    "('You ...'). (2) 3-4 sentences total. (3) Use ONLY the numerical "
    "facts you are given; no embellishment. (4) DO NOT use archetype "
    "labels: forbidden words are 'market maker', 'whale', 'novice', "
    "'expert', 'apex', 'prey', 'predator', 'pro trader', 'amateur', "
    "'shark'. Describe trading habits, sizing preferences, time horizon, "
    "and accuracy track record using neutral language."
)


log = logging.getLogger(__name__)


def _user_prompt(features: dict) -> str:
    """Build the wallet-features summary for the LLM. We intentionally
    OMIT `maker_ratio` and `avg_holding_h` because the public
    Polymarket data-api does not expose either reliably (see
    wallet_calibration.compute_features audit notes). Including them
    as the 0.0 placeholder would lead the persona LLM to fabricate
    false 'facts' like 'you are 100% taker' or 'you hold for 0 hours'."""
    cap = features["capital_usd"]
    tx = features["tx_count"]
    div = features["asset_diversity"]
    avg = features["avg_position_usd"]
    acc = features["past_accuracy"]
    n = features["n_resolved_prior"]
    return (
        f"Trader prior on-chain history (window before the target market opened):\n"
        f"- Total capital deployed: ${cap:,.0f}\n"
        f"- Trades: {tx} across {div} different markets\n"
        f"- Average position size per trade: ${avg:,.2f}\n"
        f"- Past prediction accuracy: {acc:.0%} (across {n} resolved markets)\n"
        f"\n"
        f"Write the 3-4 sentence behavioral profile per the rules above. "
        f"Do not invent facts beyond these four metrics; in particular, do "
        f"not claim anything about maker/taker behavior or holding time, "
        f"which are not in the input."
    )


def _strip_role_labels(text: str) -> str:
    """Light defense against label leakage. If the LLM did slip a
    forbidden label in, redact it by replacing with the neutral phrase
    'this trader'. Caller still gets a regex check for QA."""
    return _FORBIDDEN_RE.sub("this trader", text).strip()


def generate_profile(
    features: dict,
    api_key: str, base_url: str, model: str,
    timeout: float = 120.0, call_fn=call_deepseek,
) -> tuple[str, bool]:
    """Returns (profile_text, ok). ok=False if generation failed or the
    text contains a forbidden label after cleanup."""
    try:
        result = call_fn(
            base_url=base_url, api_key=api_key, model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_user_prompt(features),
            temperature=0.3, timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        return f"[error: {exc}]", False
    raw = result.get("text", "").strip()
    cleaned = _strip_role_labels(raw)
    ok = not _FORBIDDEN_RE.search(cleaned)
    return cleaned, ok


def load_cache(path: Path = CACHE_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: dict, path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def generate_for_market(
    target_market_id: str, force: bool = False,
    cache_path: Path = CACHE_PATH, ch: Optional[ClickHouse] = None,
) -> int:
    settings = get_settings()
    if not settings.DEEPSEEK_API_KEY:
        raise SystemExit(
            "POLYMETL_DEEPSEEK_API_KEY required (in .env) for persona generation"
        )
    if ch is None:
        ch = ClickHouse(
            host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )

    rows = ch.fetch_wallet_features(target_market_id)
    log.info("loaded %s wallet feature rows for market %s", len(rows), target_market_id)
    if not rows:
        log.warning("no wallet_features rows; run wallet_calibration first")
        return 0

    cache = load_cache(cache_path)
    market_cache = cache.setdefault(str(target_market_id), {})

    n_generated = 0
    for r in rows:
        wallet, capital_usd, tx_count, maker_ratio, avg_position_usd, \
            asset_diversity, avg_holding_h, past_accuracy, n_resolved_prior = r

        if not force and wallet in market_cache and market_cache[wallet].get("ok"):
            continue
        features = {
            "capital_usd": capital_usd, "tx_count": tx_count,
            "maker_ratio": maker_ratio, "avg_position_usd": avg_position_usd,
            "asset_diversity": asset_diversity, "avg_holding_h": avg_holding_h,
            "past_accuracy": past_accuracy, "n_resolved_prior": n_resolved_prior,
        }
        text, ok = generate_profile(
            features, api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL, model=settings.DEEPSEEK_MODEL,
        )
        market_cache[wallet] = {"profile_text": text, "ok": ok}
        n_generated += 1
        log.info(
            "[%s/%s] %s ok=%s len=%d",
            n_generated, len(rows), wallet[:10], ok, len(text),
        )
    save_cache(cache, cache_path)
    log.info("done; %s profiles generated/refreshed for market %s",
             n_generated, target_market_id)
    return n_generated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-market-id", required=True)
    parser.add_argument("--force", action="store_true",
                        help="re-generate even if cached")
    parser.add_argument("--cache-path", default=str(CACHE_PATH))
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    generate_for_market(
        target_market_id=args.target_market_id, force=args.force,
        cache_path=Path(args.cache_path),
    )


if __name__ == "__main__":
    main()
