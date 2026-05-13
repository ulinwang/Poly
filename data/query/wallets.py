"""Per-wallet pre-event activity + market-resolution lookups."""
from __future__ import annotations

from ._ch import get_ch


def list_wallets_in_market(condition_id: str, ch=None) -> list[str]:
    ch = get_ch(ch)
    rows = ch.client.execute(
        """
        SELECT DISTINCT proxy_wallet
        FROM polymetl.dataapi_trades
        WHERE condition_id = %(cid)s
        """,
        {"cid": condition_id},
    )
    return [r[0] for r in rows]


def get_pre_event_trades(
    proxy_wallet: str, cutoff_ts: int, ch=None,
) -> list[tuple]:
    """Wallet's trades strictly before cutoff_ts.
    Rows: (condition_id, outcome_index, price, size, trade_time)."""
    ch = get_ch(ch)
    return ch.client.execute(
        """
        SELECT condition_id, outcome_index, price, size, trade_time
        FROM polymetl.dataapi_trades
        WHERE proxy_wallet = %(w)s
          AND toUnixTimestamp(trade_time) < %(c)s
        """,
        {"w": proxy_wallet, "c": int(cutoff_ts)},
    )


def get_resolved_outcomes(
    condition_ids: list[str], ch=None, cutoff_ts: int | None = None,
) -> dict[str, int]:
    """Batched lookup: condition_id → winning_idx (-1 = unresolved
    or unknown).

    v13: pass ``cutoff_ts`` (unix int) to honor data hygiene; only
    markets whose ``end_date`` strictly precedes ``cutoff_ts`` are
    returned. See docs/v13/DATA_HYGIENE_AUDIT.md L-4 / L-10.
    """
    if not condition_ids:
        return {}
    ch = get_ch(ch)
    if cutoff_ts is None:
        rows = ch.client.execute(
            """
            SELECT condition_id, winning_idx
            FROM polymetl.markets_resolved FINAL
            WHERE condition_id IN %(ids)s
            """,
            {"ids": tuple(condition_ids)},
        )
    else:
        rows = ch.client.execute(
            """
            SELECT condition_id, winning_idx
            FROM polymetl.markets_resolved FINAL
            WHERE condition_id IN %(ids)s
              AND toUnixTimestamp(end_date) < %(cutoff_ts)s
            """,
            {"ids": tuple(condition_ids), "cutoff_ts": int(cutoff_ts)},
        )
    return {cid: int(idx) for cid, idx in rows}


def empirical_capital_bounds(
    condition_id: str, ch=None,
) -> tuple[float, float]:
    """p5 / p95 of `wallet_features.capital_usd` for this market.
    Used by `agent.factory` to derive capital floor/cap."""
    ch = get_ch(ch)
    rows = ch.client.execute(
        """
        SELECT quantile(0.05)(capital_usd), quantile(0.95)(capital_usd)
        FROM polymetl.wallet_features FINAL
        WHERE target_market_id = %(cid)s AND capital_usd > 0
        """,
        {"cid": condition_id},
    )
    floor, cap = rows[0] if rows else (0.0, 0.0)
    if cap is None or floor is None:
        return 0.0, 0.0
    return float(floor), float(cap)
