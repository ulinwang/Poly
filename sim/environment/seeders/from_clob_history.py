"""Seed the orderbook from the bootstrap-priors block in priors JSON.

Mirrors `environment.env.seed_orderbook_liquidity` but takes the
priors dict directly so the experiment runner can pass it through
verbatim. Owned by ENV_MAKER_AGENT_ID; SERD pipeline excludes those
nodes via the same filter as before.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def seed(sim, priors: dict) -> None:
    """Run `seed_orderbook_liquidity` with the bootstrap parameters
    from `priors`. No-op if `priors["bootstrap"]` is missing."""
    boot = priors.get("bootstrap")
    if not boot:
        log.warning("priors has no bootstrap block; skipping seed")
        return
    from environment.env import seed_orderbook_liquidity, ENV_MAKER_AGENT_ID
    yes_anchor = max(0.05, min(0.95, float(boot["anchor_yes"])))
    seed_orderbook_liquidity(
        sim,
        yes_anchor=yes_anchor, no_anchor=1.0 - yes_anchor,
        spread=float(boot.get("spread", 0.04)),
        depth_levels=int(boot.get("depth_levels", 3)),
        depth_per_level=float(boot.get("depth_per_level", 100.0)),
    )
    log.info(
        "seeded liquidity (agent_id=%d, yes_anchor=%.3f, source=%s)",
        ENV_MAKER_AGENT_ID, yes_anchor, boot.get("source", "?"),
    )
