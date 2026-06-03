"""Markets API router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from data.query._ch import get_ch
from models.market import MarketsResponse, MarketResponse, CategoriesResponse

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("", response_model=MarketsResponse)
def list_markets(q: str = "", limit: int = 30, live_only: bool = False, category: str = ""):
    ch = get_ch(None)
    pattern = f"%{q.lower()}%" if q else "%"
    rows = ch.client.execute(
        """
        SELECT cm.market_slug, cm.question, cm.condition_id,
               coalesce(mf.volume_num, 0.0) AS volume,
               mr.winning_idx,
               toString(mf.end_date) AS end_iso
        FROM polymetl.clob_markets cm
        LEFT JOIN polymetl.markets_full mf USING (condition_id)
        LEFT JOIN polymetl.markets_resolved mr USING (condition_id)
        WHERE lower(cm.market_slug) LIKE %(pat)s
           OR lower(cm.question) LIKE %(pat)s
        ORDER BY (mr.winning_idx IS NULL) DESC,
                 volume DESC
        LIMIT %(lim)s
        """,
        {"pat": pattern, "lim": int(limit)},
    )
    markets = []
    for slug, question, cid, vol, winning_idx, end_iso in rows:
        is_live = winning_idx is None or winning_idx < 0
        if live_only and not is_live:
            continue
        markets.append({
            "slug": slug,
            "question": question or "",
            "condition_id": cid,
            "volume": float(vol or 0.0),
            "is_live": bool(is_live),
            "end_date_iso": end_iso or None,
            "n_holders": None,
        })
    return {"markets": markets}


@router.get("/categories", response_model=CategoriesResponse)
def list_categories():
    return {"categories": [
        "Trending", "Breaking", "Politics", "Sports", "Crypto",
        "Esports", "Tech", "Culture", "Economy", "Weather", "Elections"
    ]}


@router.get("/{slug}", response_model=MarketResponse)
def get_market(slug: str):
    ch = get_ch(None)
    rows = ch.client.execute(
        """
        SELECT cm.market_slug, cm.question, cm.condition_id,
               coalesce(mf.volume_num, 0.0) AS volume,
               mr.winning_idx,
               toString(mf.end_date) AS end_iso,
               cm.minimum_tick_size, cm.taker_base_fee,
               cm.tokens_json
        FROM polymetl.clob_markets cm
        LEFT JOIN polymetl.markets_full mf USING (condition_id)
        LEFT JOIN polymetl.markets_resolved mr USING (condition_id)
        WHERE cm.market_slug = %(slug)s
        LIMIT 1
        """,
        {"slug": slug},
    )
    if not rows:
        raise HTTPException(404, "Market not found")
    row = rows[0]
    slug, question, cid, vol, winning_idx, end_iso, tick, fee, tokens_json = row
    import json
    tokens = json.loads(tokens_json or "[]")
    yes = next((t for t in tokens if str(t.get("outcome", "")).lower() == "yes"), {})
    no = next((t for t in tokens if str(t.get("outcome", "")).lower() == "no"), {})
    return {
        "market": {
            "slug": slug,
            "question": question or "",
            "condition_id": cid,
            "volume": float(vol or 0.0),
            "is_live": winning_idx is None or winning_idx < 0,
            "end_date_iso": end_iso or None,
            "n_holders": None,
            "tick_size": float(tick or 0.01),
            "taker_fee_bps": float(fee or 0.0),
            "description": "",
            "yes_token_id": str(yes.get("token_id", "")),
            "no_token_id": str(no.get("token_id", "")),
            "outcomes": ["Yes", "No"],
        }
    }
