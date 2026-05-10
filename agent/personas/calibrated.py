"""LLM-generated calibrated personas.

For each wallet in `wallet_features` for the target market, call
DeepSeek once with sanitized bio + features → 3-4 sentence
profile_text. Cached to `data/wallet_personas.json`.

Methodological constraint: forbidden role-typing words ("market
maker", "whale", "predator", etc.) are stripped from BOTH the LLM
output AND the wallet's self-described bio (via `sanitize_bio`)
BEFORE either reaches the LLM. SERD validation requires roles to
emerge from the network, not from initialization.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Optional

from agent.decision.llm import call_deepseek
from data.query.holders import get_bios
from data.query.wallets import list_wallets_in_market
from data.store.clickhouse import ClickHouse
from data.store.config import get_settings


CACHE_PATH = Path("data/wallet_personas.json")

FORBIDDEN_LABELS = (
    "market maker", "market-maker", "whale", "novice", "expert",
    "apex", "prey", "predator", "pro trader", "amateur", "shark",
    "sophisticated investor",
)
_FORBIDDEN_RE = re.compile(
    "|".join(re.escape(w) for w in FORBIDDEN_LABELS), re.IGNORECASE,
)
_BIO_REDACTED = "[redacted role label]"


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


def sanitize_bio(bio: str) -> str:
    """Redact forbidden role labels from a wallet bio BEFORE the LLM
    sees it. Empty/None → empty string."""
    if not bio:
        return ""
    return _FORBIDDEN_RE.sub(_BIO_REDACTED, bio).strip()


def _strip_role_labels(text: str) -> str:
    """Defense against label leakage in LLM output."""
    return _FORBIDDEN_RE.sub("this trader", text).strip()


def _user_prompt(features: dict, bio: str = "", display_name: str = "") -> str:
    cap = features["capital_usd"]
    tx = features["tx_count"]
    div = features["asset_diversity"]
    avg = features["avg_position_usd"]
    acc = features["past_accuracy"]
    n = features["n_resolved_prior"]
    parts = [
        "Trader prior on-chain history (window before the target market opened):",
        f"- Total capital deployed: ${cap:,.0f}",
        f"- Trades: {tx} across {div} different markets",
        f"- Average position size per trade: ${avg:,.2f}",
        f"- Past prediction accuracy: {acc:.0%} (across {n} resolved markets)",
    ]
    if display_name:
        parts.append(f"- Display name on Polymarket: {display_name}")
    if bio:
        parts.append(f'- Self-described bio (sanitized): "{bio}"')
    parts.append("")
    parts.append(
        "Write the 3-4 sentence behavioral profile per the rules above. "
        "Use the bio (if present) only for non-role-label colour like "
        "stated topic interests; do not promote it to an archetype. "
        "Do not invent facts beyond what's listed; in particular do not "
        "claim anything about maker/taker behavior or holding time, "
        "which are not in the input."
    )
    return "\n".join(parts)


def generate_profile(
    features: dict,
    api_key: str, base_url: str, model: str,
    bio: str = "", display_name: str = "",
    timeout: float = 120.0, call_fn=call_deepseek,
) -> tuple[str, bool]:
    """Returns (profile_text, ok). ok=False on failure or unredacted
    forbidden labels remaining after cleanup."""
    try:
        result = call_fn(
            base_url=base_url, api_key=api_key, model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_user_prompt(features, bio=bio, display_name=display_name),
            # v7: temperature pinned to 0 — see docs/EMPIRICAL_PRIORS.md.
            temperature=0.0, timeout=timeout,
        )
    except Exception as exc:                # noqa: BLE001
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
    """Top-level: fetch wallet_features rows + bios, call LLM per
    wallet, persist to JSON cache. Returns number of new profiles
    generated."""
    settings = get_settings()
    if not settings.DEEPSEEK_API_KEY:
        raise SystemExit(
            "POLYMETL_DEEPSEEK_API_KEY required for persona generation"
        )
    if ch is None:
        ch = ClickHouse(
            host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )

    rows = ch.fetch_wallet_features(target_market_id)
    log.info("loaded %d wallet_features rows for %s", len(rows), target_market_id)
    if not rows:
        log.warning(
            "no wallet_features rows; build features first via "
            "agent.features.wallet.calibrate(slug)"
        )
        return 0

    bios = get_bios(target_market_id, ch=ch)
    log.info("loaded bio/display_name for %d holders", len(bios))

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
        meta = bios.get(wallet, {})
        bio = sanitize_bio(meta.get("bio", ""))
        display_name = meta.get("display_name", "")
        text, ok = generate_profile(
            features, api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL, model=settings.DEEPSEEK_MODEL,
            bio=bio, display_name=display_name,
        )
        market_cache[wallet] = {
            "profile_text": text, "ok": ok,
            "bio_used": bio, "display_name": display_name,
        }
        n_generated += 1
        log.info(
            "[%d/%d] %s ok=%s len=%d bio=%s",
            n_generated, len(rows), wallet[:10], ok, len(text),
            "yes" if bio else "no",
        )
    save_cache(cache, cache_path)
    log.info(
        "done; %d profiles generated/refreshed for %s",
        n_generated, target_market_id,
    )
    return n_generated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-market-id", required=True,
                        help="condition_id (hex)")
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
