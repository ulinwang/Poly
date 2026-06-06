"""Markets API router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from models.market import MarketsResponse, MarketResponse, CategoriesResponse

try:
    from data.query._ch import get_ch
except Exception:
    get_ch = None

router = APIRouter(prefix="/markets", tags=["markets"])

# ---------------------------------------------------------------------------
# Mock data for local dev / demo when ClickHouse is unavailable
# ---------------------------------------------------------------------------
_MOCK_MARKETS = [
    {
        "slug": "bitcoin-100k-2024",
        "question": "Will Bitcoin hit $100,000 in 2024?",
        "condition_id": "0xbtc100k2024aaa",
        "volume": 12_450_000.0,
        "is_live": True,
        "end_date_iso": "2024-12-31T23:59:59Z",
        "n_holders": None,
        "tick_size": 0.01,
        "taker_fee_bps": 2.0,
        "description": "",
        "yes_token_id": "0xbtc_yes",
        "no_token_id": "0xbtc_no",
        "outcomes": ["Yes", "No"],
    },
    {
        "slug": "trump-win-2024",
        "question": "Will Donald Trump win the 2024 US Presidential Election?",
        "condition_id": "0xtrump2024bbb",
        "volume": 85_300_000.0,
        "is_live": True,
        "end_date_iso": "2024-11-05T23:59:59Z",
        "n_holders": None,
        "tick_size": 0.01,
        "taker_fee_bps": 2.0,
        "description": "",
        "yes_token_id": "0xtrump_yes",
        "no_token_id": "0xtrump_no",
        "outcomes": ["Yes", "No"],
    },
    {
        "slug": "fed-rate-cut-june-2024",
        "question": "Will the Fed cut rates in June 2024?",
        "condition_id": "0xfedcut2024ccc",
        "volume": 4_200_000.0,
        "is_live": False,
        "end_date_iso": "2024-06-19T23:59:59Z",
        "n_holders": None,
        "tick_size": 0.01,
        "taker_fee_bps": 2.0,
        "description": "",
        "yes_token_id": "0xfed_yes",
        "no_token_id": "0xfed_no",
        "outcomes": ["Yes", "No"],
    },
    {
        "slug": "ethereum-etf-july-2024",
        "question": "Will a spot Ethereum ETF be approved by July 2024?",
        "condition_id": "0xethjuly2024ddd",
        "volume": 9_800_000.0,
        "is_live": True,
        "end_date_iso": "2024-07-31T23:59:59Z",
        "n_holders": None,
        "tick_size": 0.01,
        "taker_fee_bps": 2.0,
        "description": "",
        "yes_token_id": "0xeth_yes",
        "no_token_id": "0xeth_no",
        "outcomes": ["Yes", "No"],
    },
    {
        "slug": "super-bowl-2024-chiefs",
        "question": "Will the Kansas City Chiefs win Super Bowl LVIII?",
        "condition_id": "0xchiefs2024eee",
        "volume": 22_100_000.0,
        "is_live": False,
        "end_date_iso": "2024-02-11T23:59:59Z",
        "n_holders": None,
        "tick_size": 0.01,
        "taker_fee_bps": 2.0,
        "description": "",
        "yes_token_id": "0xchiefs_yes",
        "no_token_id": "0xchiefs_no",
        "outcomes": ["Yes", "No"],
    },
]


def _use_mock() -> bool:
    """Return True when ClickHouse is unavailable."""
    if get_ch is None:
        return True
    try:
        # Quick connectivity probe
        ch = get_ch(None)
        ch.client.execute("SELECT 1")
        return False
    except Exception:
        return True


def _mock_list(q: str = "", limit: int = 30, live_only: bool = False) -> list[dict]:
    qlower = q.lower()
    results = [
        m for m in _MOCK_MARKETS
        if (not qlower or qlower in m["slug"] or qlower in m["question"].lower())
        and (not live_only or m["is_live"])
    ]
    return results[:limit]


def _mock_detail(slug: str) -> dict | None:
    for m in _MOCK_MARKETS:
        if m["slug"] == slug:
            return m
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("", response_model=MarketsResponse)
def list_markets(q: str = "", limit: int = 30, live_only: bool = False, category: str = ""):
    if _use_mock():
        return {"markets": _mock_list(q=q, limit=limit, live_only=live_only)}

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
    if _use_mock():
        market = _mock_detail(slug)
        if market is None:
            raise HTTPException(404, "Market not found")
        return {"market": market}

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
