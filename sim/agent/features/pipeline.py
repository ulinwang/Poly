"""Feature-pipeline orchestrator.

`build_features(slug, asof='market_open')` is the one entry point
that bundles all per-market features (priors + wallet rows + bios)
into one dict the factory can consume."""
from __future__ import annotations

import logging
from typing import Optional

from agent.features.market import derive_priors
from data.query import holders as q_holders
from data.store.clickhouse import ClickHouse

log = logging.getLogger(__name__)


def build_features(
    slug: str, asof: str = "market_open",
    include_wallet_rows: bool = True,
    include_bios: bool = False,
    ch: Optional[ClickHouse] = None,
) -> dict:
    """Bundle priors + wallet feature rows (+ optionally bios) for `slug`.

    `asof` is reserved for v9 multi-snapshot support; in v8 only
    "market_open" is supported (the priors flow uses
    `market_open_ts` from `data.query.trades`).

    v13: ``include_bios`` defaults to False — Polymarket bios are
    user-editable and can carry post-cutoff information; see
    ``docs/v13/DATA_HYGIENE_AUDIT.md`` finding L-7. The flag is kept
    for backward-compat with offline analyses that explicitly want
    bios but should not be flipped for simulation runs.
    """
    if asof != "market_open":
        raise NotImplementedError(
            f"asof={asof!r}; only 'market_open' is supported in v8"
        )
    priors = derive_priors(slug, ch=ch)
    out: dict = {"priors": priors}
    if include_wallet_rows:
        from data.query._ch import get_ch
        ch_eff = get_ch(ch)
        out["wallet_features"] = ch_eff.fetch_wallet_features(
            priors["condition_id"]
        )
    if include_bios:
        out["bios"] = q_holders.get_bios(priors["condition_id"], ch=ch)
    log.info(
        "built features for %s: priors_source=%s, %d wallets, %d bios",
        slug, priors["signal_mu_meta"]["source"],
        len(out.get("wallet_features", [])), len(out.get("bios", {})),
    )
    return out
