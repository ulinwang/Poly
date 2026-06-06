"""Test markets router mock fallback when ClickHouse is unavailable."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

# Force mock mode by temporarily hiding the real get_ch import path
import routers.markets as markets_module
markets_module.get_ch = None

from routers.markets import router


def _call_sync(func, **kwargs):
    """Call a sync FastAPI dependency / endpoint directly."""
    return func(**kwargs)


def test_list_markets_mock():
    data = _call_sync(router.routes[0].endpoint, q="", limit=5, live_only=False, category="")
    assert "markets" in data
    assert len(data["markets"]) >= 3
    m = data["markets"][0]
    assert "slug" in m
    assert "question" in m
    assert "condition_id" in m
    assert "volume" in m
    assert "is_live" in m


def test_list_markets_mock_search():
    data = _call_sync(router.routes[0].endpoint, q="bitcoin", limit=30, live_only=False, category="")
    assert all("bitcoin" in (m["slug"] + m["question"]).lower() for m in data["markets"])


def test_list_markets_mock_live_only():
    data = _call_sync(router.routes[0].endpoint, q="", limit=30, live_only=True, category="")
    assert all(m["is_live"] for m in data["markets"])


def test_get_market_mock():
    data = _call_sync(router.routes[2].endpoint, slug="bitcoin-100k-2024")
    assert "market" in data
    m = data["market"]
    assert m["slug"] == "bitcoin-100k-2024"
    assert "tick_size" in m
    assert "taker_fee_bps" in m
    assert "yes_token_id" in m
    assert "no_token_id" in m
    assert m["outcomes"] == ["Yes", "No"]


def test_get_market_mock_404():
    from fastapi import HTTPException
    try:
        _call_sync(router.routes[2].endpoint, slug="nonexistent-market")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected 404")
