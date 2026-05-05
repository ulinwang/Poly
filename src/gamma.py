from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any, Iterator, Optional, Sequence

from .clickhouse_client import ClickHouse
from .config import get_settings


GAMMA_BASE = "https://gamma-api.polymarket.com"
USER_AGENT = "polymetl-gamma/0.1 (+https://github.com/polymetl)"
log = logging.getLogger(__name__)


def fetch_markets_page(
    limit: int = 500,
    offset: int = 0,
    closed: Optional[bool] = None,
    base: str = GAMMA_BASE,
    timeout: float = 30.0,
) -> list[dict]:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if closed is not None:
        params["closed"] = "true" if closed else "false"
    url = f"{base}/markets?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    return list(payload) if payload else []


def iter_all_markets(
    page_size: int = 500,
    closed: Optional[bool] = None,
    sleep: float = 0.2,
    fetch_fn=fetch_markets_page,
) -> Iterator[dict]:
    offset = 0
    while True:
        page = fetch_fn(limit=page_size, offset=offset, closed=closed)
        if not page:
            return
        for m in page:
            yield m
        if len(page) < page_size:
            return
        offset += page_size
        if sleep:
            time.sleep(sleep)


def _parse_json_array(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _parse_datetime(value: Any) -> Optional[dt.datetime]:
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value.replace(tzinfo=None)
    if not isinstance(value, str):
        return None
    s = value.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        return None


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def market_to_row(m: dict, fetched_at: Optional[dt.datetime] = None) -> tuple:
    fetched_at = fetched_at or dt.datetime.utcnow()
    outcomes = [str(x) for x in _parse_json_array(m.get("outcomes"))]
    clob_token_ids = [str(x) for x in _parse_json_array(m.get("clobTokenIds"))]
    outcome_prices = [_to_float(x) for x in _parse_json_array(m.get("outcomePrices"))]
    end_date = _parse_datetime(
        m.get("endDate") or m.get("end_date_iso") or m.get("endDateIso")
    )
    return (
        str(m.get("id", "")),
        str(m.get("slug", "") or ""),
        str(m.get("question", "") or ""),
        str(m.get("description", "") or ""),
        str(m.get("category", "") or ""),
        outcomes,
        clob_token_ids,
        outcome_prices,
        _to_float(m.get("volume")),
        end_date,
        1 if m.get("active") else 0,
        1 if m.get("closed") else 0,
        fetched_at,
    )


def run(
    closed: Optional[bool] = None,
    page_size: int = 500,
    batch_size: int = 1000,
    ch: Optional[ClickHouse] = None,
) -> int:
    if ch is None:
        settings = get_settings()
        ch = ClickHouse(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )
    ch.ensure_markets_schema()

    buffer: list[tuple] = []
    total = 0
    for m in iter_all_markets(page_size=page_size, closed=closed):
        buffer.append(market_to_row(m))
        if len(buffer) >= batch_size:
            ch.insert_markets(buffer)
            total += len(buffer)
            log.info("inserted %s markets (total %s)", len(buffer), total)
            buffer = []
    if buffer:
        ch.insert_markets(buffer)
        total += len(buffer)
    log.info("done; total markets inserted: %s", total)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pull Polymarket markets via Gamma API into ClickHouse"
    )
    parser.add_argument(
        "--closed",
        choices=["true", "false", "all"],
        default="all",
        help="Filter by closed flag",
    )
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    closed = None if args.closed == "all" else (args.closed == "true")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run(closed=closed, page_size=args.page_size, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
