"""Full-platform maker→taker capital-flow network across ALL markets.

Distinct from `experiments/analysis/serd.py` (which builds the
network on ONE simulation's `agent_fills`). This module is for
data-layer offline analysis of real Polymarket activity, e.g. for
understanding the population baseline before sim calibration.

v8: scaffold only. Returns the schema + a `summary()` stub. Heavy
lifting (pyvis / networkx) lands in v9 if needed.
"""
from __future__ import annotations

import logging

from data.query._ch import get_ch

log = logging.getLogger(__name__)


def maker_taker_edge_summary(ch=None) -> dict:
    """One-shot: count edges in `dataapi_trades` aggregated to
    (maker, taker, condition_id) — useful as a sanity check on
    network density.

    Note: data-api does NOT expose maker vs taker per trade (the
    `takerOnly` query parameter merely toggles whether the user
    appears as taker). This stub therefore counts wallet-pair
    co-occurrence rather than true maker→taker flows. Real
    maker/taker comes from on-chain `OrderFilled.maker` /
    `.taker` fields once `data.sources.onchain` is implemented.
    """
    ch = get_ch(ch)
    rows = ch.client.execute(
        """
        SELECT count(), uniqExact(proxy_wallet),
               uniqExact(condition_id)
        FROM polymetl.dataapi_trades
        """
    )
    n_trades, n_wallets, n_markets = rows[0] if rows else (0, 0, 0)
    return {
        "n_trades": int(n_trades),
        "n_wallets": int(n_wallets),
        "n_markets": int(n_markets),
        "note": (
            "Maker/taker labels are NOT available from data-api; "
            "true network is pending data.sources.onchain ingest."
        ),
    }


def main() -> None:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    s = maker_taker_edge_summary()
    print(f"trades:  {s['n_trades']:,}")
    print(f"wallets: {s['n_wallets']:,}")
    print(f"markets: {s['n_markets']:,}")
    print(f"note:    {s['note']}")


if __name__ == "__main__":
    main()
