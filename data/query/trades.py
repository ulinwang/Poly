"""Per-trade reads + first-window VWAP for the signal_mu prior."""
from __future__ import annotations

import logging
from typing import Optional

from ._ch import get_ch

log = logging.getLogger(__name__)


def market_open_ts(condition_id: str, ch=None) -> int:
    """Unix timestamp of the FIRST trade in `condition_id`.
    Raises SystemExit if the market has zero trades."""
    ch = get_ch(ch)
    rows = ch.client.execute(
        """
        SELECT min(trade_time) FROM polymetl.dataapi_trades
        WHERE condition_id = %(cid)s
        """,
        {"cid": condition_id},
    )
    if not rows or rows[0][0] is None:
        raise SystemExit(
            f"no trades in dataapi_trades for {condition_id}; "
            f"ingest data_api first"
        )
    return int(rows[0][0].timestamp())


def market_last_trade_ts(condition_id: str, ch=None) -> Optional[int]:
    ch = get_ch(ch)
    rows = ch.client.execute(
        """
        SELECT max(trade_time) FROM polymetl.dataapi_trades
        WHERE condition_id = %(cid)s
        """,
        {"cid": condition_id},
    )
    if not rows or rows[0][0] is None:
        return None
    return int(rows[0][0].timestamp())


def first_window_vwap(
    condition_id: str, outcome_index: int, t0: int, hours: int = 24,
    ch=None,
) -> dict:
    """Volume-weighted average price for `outcome_index` (0=Yes,
    1=No) over the first `hours` after `t0`. Returns
    {"vwap", "n_trades", "source": "dataapi_trades", "hours"}.
    """
    ch = get_ch(ch)
    cutoff = t0 + hours * 3600
    rows = ch.client.execute(
        """
        SELECT count(), sum(price * size) AS w, sum(size) AS s
        FROM polymetl.dataapi_trades
        WHERE condition_id = %(cid)s
          AND outcome_index = %(oidx)s
          AND toUnixTimestamp(trade_time) >= %(o)s
          AND toUnixTimestamp(trade_time) < %(c)s
        """,
        {"cid": condition_id, "oidx": int(outcome_index),
         "o": int(t0), "c": int(cutoff)},
    )
    n, w, s = rows[0] if rows else (0, 0.0, 0.0)
    if n and s and float(s) > 0:
        return {"vwap": float(w) / float(s), "n_trades": int(n),
                "source": "dataapi_trades", "hours": hours}
    return {"vwap": 0.5, "n_trades": 0,
            "source": "fallback_0.5", "hours": hours}


def trade_dispersion(
    condition_id: str, outcome_index: int, t0: int, hours: int = 24,
    ch=None,
) -> dict:
    """Mean / IQR of trade prices + median size in the first window.
    Used as bootstrap fallback when clob_orderbook is empty."""
    ch = get_ch(ch)
    cutoff = t0 + hours * 3600
    rows = ch.client.execute(
        """
        SELECT count(), avg(price), quantile(0.25)(price),
               quantile(0.75)(price), quantile(0.5)(size)
        FROM polymetl.dataapi_trades
        WHERE condition_id = %(cid)s
          AND outcome_index = %(oidx)s
          AND toUnixTimestamp(trade_time) >= %(o)s
          AND toUnixTimestamp(trade_time) < %(c)s
        """,
        {"cid": condition_id, "oidx": int(outcome_index),
         "o": int(t0), "c": int(cutoff)},
    )
    n, mean_p, q25, q75, depth = rows[0] if rows else (0, 0.5, 0.4, 0.6, 100.0)
    return {
        "n": int(n), "mean": float(mean_p or 0.5),
        "q25": float(q25 or 0.4), "q75": float(q75 or 0.6),
        "median_size": float(depth or 100.0),
    }


def get_trades(
    condition_id: str, since_ts: Optional[int] = None,
    until_ts: Optional[int] = None, outcome_index: Optional[int] = None,
    ch=None,
) -> list[tuple]:
    """All trades for a market, optionally bounded.
    Rows: (trade_time, outcome_index, price, size, proxy_wallet)."""
    ch = get_ch(ch)
    where = ["condition_id = %(cid)s"]
    params: dict = {"cid": condition_id}
    if since_ts is not None:
        where.append("toUnixTimestamp(trade_time) >= %(since)s")
        params["since"] = int(since_ts)
    if until_ts is not None:
        where.append("toUnixTimestamp(trade_time) < %(until)s")
        params["until"] = int(until_ts)
    if outcome_index is not None:
        where.append("outcome_index = %(oidx)s")
        params["oidx"] = int(outcome_index)
    return ch.client.execute(
        f"""
        SELECT trade_time, outcome_index, price, size, proxy_wallet
        FROM polymetl.dataapi_trades
        WHERE {' AND '.join(where)}
        ORDER BY trade_time
        """,
        params,
    )
