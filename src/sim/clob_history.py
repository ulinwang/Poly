"""
Fetch real Polymarket trade history for a given outcome token id from
the public Polymarket data-api. Used to compare simulator output against
actual market behavior.

Endpoint: GET https://data-api.polymarket.com/trades?market=<token_id>

The endpoint paginates by `offset` and `limit`. Each trade has:
  proxyWallet (taker), side (BUY/SELL of YES tokens — direction of the
    user, not the market), outcome ('Yes'/'No'), price, size,
    timestamp (unix), transactionHash.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator, Optional


DATA_API_BASE = "https://data-api.polymarket.com"
USER_AGENT = "polymetl-sim/0.1"

log = logging.getLogger(__name__)


def fetch_trades_page(
    token_id: str,
    limit: int = 500,
    offset: int = 0,
    base: str = DATA_API_BASE,
    timeout: float = 30.0,
) -> list[dict]:
    params = {"market": token_id, "limit": limit, "offset": offset}
    url = f"{base}/trades?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    return list(payload) if payload else []


def iter_all_trades(
    token_id: str,
    page_size: int = 500,
    sleep: float = 0.2,
    fetch_fn=fetch_trades_page,
) -> Iterator[dict]:
    offset = 0
    while True:
        try:
            page = fetch_fn(token_id=token_id, limit=page_size, offset=offset)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 422):
                log.warning("data-api rejected offset=%s with HTTP %s; stopping",
                            offset, exc.code)
                return
            raise
        if not page:
            return
        for t in page:
            yield t
        if len(page) < page_size:
            return
        offset += page_size
        if sleep:
            time.sleep(sleep)


def trade_to_row(
    trade: dict,
    market_id: str,
    token_id: str,
    fetched_at: dt.datetime,
) -> tuple:
    ts = trade.get("timestamp") or trade.get("ts") or 0
    try:
        trade_time = dt.datetime.utcfromtimestamp(int(ts))
    except (TypeError, ValueError, OSError):
        trade_time = dt.datetime.utcfromtimestamp(0)
    side = str(trade.get("side") or "")
    try:
        price = float(trade.get("price") or 0)
    except (TypeError, ValueError):
        price = 0.0
    try:
        size = float(trade.get("size") or 0)
    except (TypeError, ValueError):
        size = 0.0
    maker = str(trade.get("makerAddress") or trade.get("maker") or "")
    taker = str(trade.get("proxyWallet") or trade.get("taker") or trade.get("user") or "")
    return (market_id, token_id, trade_time, side, price, size, maker, taker, fetched_at)


def fetch_and_store_trades(
    ch,
    market_id: str,
    token_id: str,
    page_size: int = 500,
    insert_batch: int = 1000,
) -> int:
    """Pull all trades for `token_id` and write to market_trade_history.
    Returns the number of trades inserted."""
    fetched_at = dt.datetime.utcnow()
    buffer: list[tuple] = []
    total = 0
    for trade in iter_all_trades(token_id, page_size=page_size):
        buffer.append(trade_to_row(trade, market_id, token_id, fetched_at))
        if len(buffer) >= insert_batch:
            ch.insert_trade_history(buffer)
            total += len(buffer)
            log.info("inserted %s trades for token %s (total %s)",
                     len(buffer), token_id[:12] + "...", total)
            buffer = []
    if buffer:
        ch.insert_trade_history(buffer)
        total += len(buffer)
    log.info("done; %s trades inserted for token %s", total, token_id[:12] + "...")
    return total
