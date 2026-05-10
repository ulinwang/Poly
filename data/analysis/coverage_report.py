"""Print row counts + freshness per ClickHouse table.

Use to refresh `docs/DATA_INVENTORY.md` after a fresh ingest run.

CLI:
    python -m data.analysis.coverage_report
    python -m data.analysis.coverage_report --as-of 2026-05-10
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging

from data.query._ch import get_ch

log = logging.getLogger(__name__)

# Tables this project owns. Order matches DATA_INVENTORY.md.
TABLES = [
    "markets_full",
    "clob_markets",
    "clob_orderbook",
    "clob_quotes",
    "clob_prices_history",
    "dataapi_trades",
    "dataapi_holders",
    "dataapi_oi",
    "wallet_features",
    "agent_simulations",
    "agent_actions",
    "agent_fills",
    "agent_positions",
    "agent_personas",
    "serd_results",
    # v8 scaffold (will populate post-onchain ingest):
    "onchain_order_filled",
    "onchain_orders_matched",
    "onchain_split",
    "onchain_merge",
    "onchain_redeem",
]


def gather(ch=None) -> list[dict]:
    """Returns one dict per table: {table, rows, latest_row}."""
    ch = get_ch(ch)
    out: list[dict] = []
    for t in TABLES:
        try:
            rows = ch.client.execute(f"SELECT count() FROM polymetl.{t}")
            n = int(rows[0][0]) if rows else 0
        except Exception:        # noqa: BLE001
            n = -1   # table missing
        latest = None
        if n > 0:
            latest_col = _latest_col(t)
            if latest_col:
                try:
                    rows = ch.client.execute(
                        f"SELECT max({latest_col}) FROM polymetl.{t}"
                    )
                    latest = rows[0][0]
                except Exception:        # noqa: BLE001
                    pass
        out.append({"table": t, "rows": n, "latest_row": latest})
    return out


def _latest_col(table: str) -> str | None:
    """Best-guess column for "freshness" per table."""
    if table.startswith("agent_"):
        return None    # uses sim_id; freshness via agent_simulations.started_at
    if table in ("wallet_features", "serd_results"):
        return "fetched_at"
    if table in ("dataapi_trades", "dataapi_holders"):
        return "fetched_at"
    if table.startswith("clob_"):
        return "fetched_at"
    if table == "markets_full":
        return "fetched_at"
    if table.startswith("onchain_"):
        return "block_time"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None,
                        help="ISO date, default = today")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    asof = args.as_of or dt.date.today().isoformat()
    print(f"# Coverage report — {asof}")
    print()
    print(f"{'Table':<30} {'Rows':>14}  Latest")
    print("-" * 80)
    for r in gather():
        n = r["rows"]
        n_str = f"{n:,}" if n >= 0 else "(missing)"
        print(f"{r['table']:<30} {n_str:>14}  {r['latest_row'] or '-'}")


if __name__ == "__main__":
    main()
