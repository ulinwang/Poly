"""Orderbook snapshots (clob_orderbook) reads + bootstrap priors."""
from __future__ import annotations

import logging
from typing import Optional

from ._ch import get_ch

log = logging.getLogger(__name__)


def get_book_snapshot(
    token_id: str, at_unix: Optional[int] = None, ch=None,
) -> list[tuple]:
    """Latest snapshot ≤ `at_unix` (None = latest). Rows are
    (side, price, size, fetched_at) for the chosen book_timestamp."""
    ch = get_ch(ch)
    if at_unix is None:
        rows = ch.client.execute(
            """
            SELECT side, price, size, fetched_at
            FROM polymetl.clob_orderbook
            WHERE token_id = %(tid)s
              AND fetched_at = (
                SELECT max(fetched_at) FROM polymetl.clob_orderbook
                WHERE token_id = %(tid)s
              )
            """,
            {"tid": token_id},
        )
    else:
        rows = ch.client.execute(
            """
            SELECT side, price, size, fetched_at
            FROM polymetl.clob_orderbook
            WHERE token_id = %(tid)s
              AND toUnixTimestamp(fetched_at) <= %(at)s
              AND fetched_at = (
                SELECT max(fetched_at) FROM polymetl.clob_orderbook
                WHERE token_id = %(tid)s
                  AND toUnixTimestamp(fetched_at) <= %(at)s
              )
            """,
            {"tid": token_id, "at": int(at_unix)},
        )
    return rows


def bootstrap_priors(
    token_id: str, t0: int, hours: int = 24, ch=None,
) -> Optional[dict]:
    """First-window orderbook stats from `clob_orderbook`. Returns
    None if the table has no rows for this token in the window
    (caller should fall back to trade dispersion via trades.py).
    """
    ch = get_ch(ch)
    cutoff = t0 + hours * 3600
    rows = ch.client.execute(
        """
        SELECT
            avg(if(side='BUY',  price, NULL)) AS bid_avg,
            avg(if(side='SELL', price, NULL)) AS ask_avg,
            quantile(0.5)(size) AS depth_med
        FROM polymetl.clob_orderbook
        WHERE token_id = %(tid)s
          AND toUnixTimestamp(fetched_at) >= %(o)s
          AND toUnixTimestamp(fetched_at) < %(c)s
        """,
        {"tid": token_id, "o": int(t0), "c": int(cutoff)},
    )
    bid, ask, depth = rows[0] if rows else (None, None, None)
    if bid is None or ask is None or not depth or float(depth) <= 0:
        return None
    return {
        "anchor_yes": (float(bid) + float(ask)) / 2.0,
        "spread": max(0.01, float(ask) - float(bid)),
        "depth_per_level": float(depth),
        "depth_levels": 3,
        "source": "clob_orderbook",
    }
