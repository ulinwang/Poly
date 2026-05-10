"""dataapi_holders reads — bios, display names, top holders."""
from __future__ import annotations

from ._ch import get_ch


def get_bios(condition_id: str, ch=None) -> dict[str, dict]:
    """Map proxy_wallet → {display_name, bio}. Bios are RAW
    (un-sanitized); the sanitization happens in
    `agent/personas/calibrated.py` before they reach the LLM."""
    ch = get_ch(ch)
    rows = ch.client.execute(
        """
        SELECT proxy_wallet, any(display_name), any(bio)
        FROM polymetl.dataapi_holders FINAL
        WHERE condition_id = %(cid)s
        GROUP BY proxy_wallet
        """,
        {"cid": condition_id},
    )
    return {
        w: {"display_name": (dn or "").strip(), "bio": (bio or "").strip()}
        for w, dn, bio in rows
    }


def get_top_holders(
    condition_id: str, k: int = 100, ch=None,
) -> list[tuple]:
    """Top-k holders by amount across both outcomes.
    Rows: (proxy_wallet, outcome_index, amount, display_name)."""
    ch = get_ch(ch)
    return ch.client.execute(
        """
        SELECT proxy_wallet, outcome_index, sum(amount) AS amt,
               any(display_name)
        FROM polymetl.dataapi_holders FINAL
        WHERE condition_id = %(cid)s
        GROUP BY proxy_wallet, outcome_index
        ORDER BY amt DESC
        LIMIT %(k)s
        """,
        {"cid": condition_id, "k": int(k)},
    )
