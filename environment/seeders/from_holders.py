"""Seed each agent with a starting position matching their real
holdings on the target market.

Reads `data.query.holders.get_top_holders` to look up
(proxy_wallet → outcome_index, amount) and credits matched agents
their pre-event share count. Not used by the v7 reference run
(agents start cash-only) but supported via experiments/configs/*.yaml.

v8 implementation: matches agents by `src_wallet_addr`. Wallets in
the calibrated population that don't appear in the holders table
keep their default zero starting position.
"""
from __future__ import annotations

import logging

from data.query import holders as q_holders

log = logging.getLogger(__name__)


def seed(sim, condition_id: str) -> int:
    """Credit each agent with shares matching their on-chain holdings
    at calibration cutoff. Returns the number of agents seeded."""
    rows = q_holders.get_top_holders(condition_id, k=10_000)
    by_wallet: dict[str, dict[str, float]] = {}
    for wallet, oidx, amount, _name in rows:
        by_wallet.setdefault(wallet, {"YES": 0.0, "NO": 0.0})
        by_wallet[wallet]["YES" if int(oidx) == 0 else "NO"] += float(amount)

    n = 0
    for agent in sim.agents:
        addr = getattr(agent, "src_wallet_addr", "")
        if not addr:
            continue
        pos = by_wallet.get(addr)
        if not pos:
            continue
        agent.yes_shares += pos["YES"]
        agent.no_shares += pos["NO"]
        n += 1
    log.info("seeded %d agents from dataapi_holders for %s",
             n, condition_id[:18])
    return n
