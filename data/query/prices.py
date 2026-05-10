"""clob_prices_history reads (hourly bars)."""
from __future__ import annotations

from typing import Optional

from ._ch import get_ch


def get_price_history(
    token_id: str, since_ts: Optional[int] = None,
    until_ts: Optional[int] = None, ch=None,
) -> list[tuple]:
    """Rows: (t, p) sorted by t."""
    ch = get_ch(ch)
    where = ["token_id = %(tid)s"]
    params: dict = {"tid": token_id}
    if since_ts is not None:
        where.append("toUnixTimestamp(t) >= %(since)s")
        params["since"] = int(since_ts)
    if until_ts is not None:
        where.append("toUnixTimestamp(t) < %(until)s")
        params["until"] = int(until_ts)
    return ch.client.execute(
        f"""
        SELECT t, p
        FROM polymetl.clob_prices_history
        WHERE {' AND '.join(where)}
        ORDER BY t
        """,
        params,
    )


def first_window_avg(
    token_id: str, t0: int, hours: int = 24, ch=None,
) -> Optional[dict]:
    """Mean price + sample size in the first `hours`. Returns None
    if zero rows (caller falls back to trade VWAP)."""
    ch = get_ch(ch)
    cutoff = t0 + hours * 3600
    rows = ch.client.execute(
        """
        SELECT count(), avg(p)
        FROM polymetl.clob_prices_history
        WHERE token_id = %(tid)s
          AND toUnixTimestamp(t) >= %(o)s
          AND toUnixTimestamp(t) < %(c)s
        """,
        {"tid": token_id, "o": int(t0), "c": int(cutoff)},
    )
    n, avg_p = rows[0] if rows else (0, None)
    if not n or avg_p is None:
        return None
    return {"vwap": float(avg_p), "n_trades": int(n),
            "source": "clob_prices_history", "hours": hours}
