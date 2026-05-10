"""Market metadata + slug→condition_id + resolved-market selection."""
from __future__ import annotations

import json
from typing import Optional

from ._ch import get_ch


def get_market_meta(slug: str, ch=None) -> Optional[dict]:
    """Resolve `slug` → market metadata. Returns None if unknown.

    Joins `clob_markets` (slug, tokens_json, tick_size, fee) with
    `markets_resolved` (winning_idx, end_date) and `markets_full`
    (description, volume).
    """
    ch = get_ch(ch)
    rows = ch.client.execute(
        """
        SELECT cm.condition_id, cm.market_slug, cm.question,
               cm.tokens_json, cm.minimum_tick_size, cm.taker_base_fee,
               cm.end_date_iso, cm.accepting_order_timestamp,
               mr.winning_idx, mr.end_date, mr.outcomes,
               mf.description, mf.volume_num
        FROM polymetl.clob_markets cm
        LEFT JOIN polymetl.markets_resolved mr USING (condition_id)
        LEFT JOIN polymetl.markets_full mf USING (condition_id)
        WHERE cm.market_slug = %(slug)s
        LIMIT 1
        """,
        {"slug": slug},
    )
    if not rows:
        return None
    cid, slug_, question, tokens_json, tick, fee, end_iso, accept_ts, \
        win_idx, end_date, outcomes, description, volume = rows[0]
    tokens = json.loads(tokens_json or "[]")
    yes = next((t for t in tokens if str(t.get("outcome", "")).lower() == "yes"),
               tokens[0] if tokens else {})
    no = next((t for t in tokens if str(t.get("outcome", "")).lower() == "no"),
              tokens[-1] if tokens else {})
    return {
        "condition_id": cid,
        "slug": slug_,
        "question": question or "",
        "description": description or "",
        "yes_token_id": str(yes.get("token_id", "")),
        "no_token_id": str(no.get("token_id", "")),
        "outcomes": list(outcomes) if outcomes else ["Yes", "No"],
        "tick_size": float(tick),
        "taker_fee_bps": float(fee),
        "end_date": end_date,
        "end_date_iso": end_iso.isoformat() if end_iso else None,
        "accept_ts_iso": accept_ts.isoformat() if accept_ts else None,
        "winning_idx": int(win_idx) if win_idx is not None else -1,
        "volume": float(volume or 0.0),
    }


def select_resolved_markets(
    *,
    min_volume: float = 5_000.0,
    max_volume: float = 5_000_000.0,
    min_wallets: int = 30,
    end_after_iso: Optional[str] = None,
    end_before_iso: Optional[str] = None,
    require_binary: bool = True,
    limit: int = 50,
    ch=None,
) -> list[tuple]:
    """Candidate resolved markets matching criteria. Returns
    [(slug, condition_id, volume, n_wallets, end_date, question), ...].
    Ordered by n_wallets desc, then volume desc."""
    ch = get_ch(ch)
    where = ["mf.volume_num >= %(vmin)s", "mf.volume_num <= %(vmax)s"]
    params: dict = {
        "vmin": min_volume, "vmax": max_volume,
        "limit": int(limit), "min_wallets": int(min_wallets),
    }
    if end_after_iso:
        where.append("mr.end_date >= toDateTime(%(end_after)s)")
        params["end_after"] = end_after_iso
    if end_before_iso:
        where.append("mr.end_date <= toDateTime(%(end_before)s)")
        params["end_before"] = end_before_iso
    if require_binary:
        where.append("length(mr.outcomes) = 2")
    where_sql = " AND ".join(where)
    return ch.client.execute(
        f"""
        SELECT mr.slug, mr.condition_id, mf.volume_num,
               uniqExact(t.proxy_wallet) AS n_wallets,
               mr.end_date, mr.question
        FROM polymetl.markets_resolved mr
        INNER JOIN polymetl.markets_full mf USING (condition_id)
        INNER JOIN polymetl.dataapi_trades t
            ON t.condition_id = mr.condition_id
        WHERE {where_sql}
        GROUP BY mr.slug, mr.condition_id, mf.volume_num,
                 mr.end_date, mr.question
        HAVING n_wallets >= %(min_wallets)s
        ORDER BY n_wallets DESC, mf.volume_num DESC
        LIMIT %(limit)s
        """,
        params,
    )
