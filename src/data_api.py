"""
Crawl Polymarket data-api (https://data-api.polymarket.com) for every
known conditionId and persist responses into ClickHouse.

Endpoints crawled (one row in clickhouse_client.py-equivalent helpers below
per endpoint, all defined inline to keep this module self-contained):

  /trades?market=<conditionId>&limit=1000&offset=N  (offset cap 3000)
      → polymetl.dataapi_trades
  /holders?market=<conditionId>&limit=1000          (top holders per outcome)
      → polymetl.dataapi_holders
  /oi?market=<conditionId>                          (current open interest)
      → polymetl.dataapi_oi

Resume: each endpoint has a per-conditionId progress table
polymetl.dataapi_progress so re-runs skip already-processed markets.

Usage:
    uv run python -m src.data_api --endpoint trades  --workers 30
    uv run python -m src.data_api --endpoint holders --workers 30
    uv run python -m src.data_api --endpoint oi      --workers 50
    uv run python -m src.data_api --endpoint all     --workers 30
    uv run python -m src.data_api --endpoint oi --markets-limit 100   # smoke
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional, Sequence

from .clickhouse_client import ClickHouse
from .config import get_settings


DATA_API_BASE = "https://data-api.polymarket.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Accept": "application/json,*/*",
    "Origin": "https://polymarket.com",
    "Referer": "https://polymarket.com/",
}

PAGE_SIZE = 1000
OFFSET_CAP = 3000           # data-api caps historical offset at 3000
HOLDERS_LIMIT = 1000        # max holders per outcome the API returns

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------
def ensure_dataapi_schemas(ch: ClickHouse) -> None:
    db = ch.database

    ch.client.execute(f"""
        CREATE TABLE IF NOT EXISTS {db}.dataapi_trades (
            condition_id      String,
            tx_hash           String,
            trade_time        DateTime,
            proxy_wallet      String,
            side              LowCardinality(String),
            asset             String,
            size              Float64,
            price             Float64,
            outcome           LowCardinality(String),
            outcome_index     UInt8,
            title             String,
            slug              String,
            event_slug        String,
            icon              String,
            display_name      String,
            pseudonym         String,
            bio               String,
            profile_image     String,
            profile_image_optimized String,
            fetched_at        DateTime
        )
        ENGINE = ReplacingMergeTree(fetched_at)
        PARTITION BY toYYYYMM(trade_time)
        ORDER BY (condition_id, trade_time, tx_hash, asset, proxy_wallet)
        SETTINGS index_granularity = 8192
    """)

    ch.client.execute(f"""
        CREATE TABLE IF NOT EXISTS {db}.dataapi_holders (
            condition_id      String,
            asset             String,
            outcome_index     UInt8,
            proxy_wallet      String,
            amount            Float64,
            display_name      String,
            pseudonym         String,
            bio               String,
            profile_image     String,
            profile_image_optimized String,
            verified          UInt8,
            display_username_public UInt8,
            fetched_at        DateTime
        )
        ENGINE = ReplacingMergeTree(fetched_at)
        ORDER BY (condition_id, asset, proxy_wallet)
        SETTINGS index_granularity = 8192
    """)

    ch.client.execute(f"""
        CREATE TABLE IF NOT EXISTS {db}.dataapi_oi (
            market            String,
            value             Float64,
            fetched_at        DateTime
        )
        ENGINE = ReplacingMergeTree(fetched_at)
        ORDER BY market
        SETTINGS index_granularity = 8192
    """)

    ch.client.execute(f"""
        CREATE TABLE IF NOT EXISTS {db}.dataapi_progress (
            endpoint          LowCardinality(String),
            condition_id      String,
            row_count         UInt32,
            updated_at        DateTime
        )
        ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY (endpoint, condition_id)
        SETTINGS index_granularity = 8192
    """)


# ---------------------------------------------------------------------------
# HTTP fetcher with retry/backoff
# ---------------------------------------------------------------------------
def http_get(path: str, timeout: float = 20.0,
             max_retries: int = 5) -> Any:
    """GET with retry on 429 / 5xx / network errors. Returns parsed JSON."""
    url = DATA_API_BASE + path
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                last_exc = e
                time.sleep(min(2 ** attempt + 0.5, 30))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_exc = e
            time.sleep(min(2 ** attempt + 0.5, 30))
    raise RuntimeError(f"GET {url} failed after {max_retries} retries: {last_exc!r}")


# ---------------------------------------------------------------------------
# Per-endpoint fetchers + row builders
# ---------------------------------------------------------------------------
def _fmt_str(v: Any) -> str:
    return "" if v is None else str(v)


def _fmt_int(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _fmt_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fmt_bool(v: Any) -> int:
    return 1 if bool(v) else 0


def fetch_trades(condition_id: str) -> list[dict]:
    """All historical trades for a market, capped at 3,000 rows."""
    out: list[dict] = []
    for offset in range(0, OFFSET_CAP, PAGE_SIZE):
        try:
            page = http_get(
                f"/trades?market={condition_id}&limit={PAGE_SIZE}&offset={offset}"
            )
        except urllib.error.HTTPError as e:
            if e.code in (400, 422):
                break
            raise
        if not isinstance(page, list) or not page:
            break
        out.extend(page)
        if len(page) < PAGE_SIZE:
            break
    return out


def trade_to_row(t: dict, fetched_at: dt.datetime) -> tuple:
    ts = _fmt_int(t.get("timestamp"))
    try:
        trade_time = dt.datetime.utcfromtimestamp(ts) if ts > 0 else dt.datetime(1970, 1, 1)
    except (OSError, ValueError):
        trade_time = dt.datetime(1970, 1, 1)
    return (
        _fmt_str(t.get("conditionId")),
        _fmt_str(t.get("transactionHash")),
        trade_time,
        _fmt_str(t.get("proxyWallet")).lower(),
        _fmt_str(t.get("side")),
        _fmt_str(t.get("asset")),
        _fmt_float(t.get("size")),
        _fmt_float(t.get("price")),
        _fmt_str(t.get("outcome")),
        _fmt_int(t.get("outcomeIndex")),
        _fmt_str(t.get("title")),
        _fmt_str(t.get("slug")),
        _fmt_str(t.get("eventSlug")),
        _fmt_str(t.get("icon")),
        _fmt_str(t.get("name")),
        _fmt_str(t.get("pseudonym")),
        _fmt_str(t.get("bio")),
        _fmt_str(t.get("profileImage")),
        _fmt_str(t.get("profileImageOptimized")),
        fetched_at,
    )


def fetch_holders(condition_id: str) -> list[dict]:
    """Top holders for each outcome of the market (max 1000 per outcome).

    The API returns a list of {token, holders:[...]} objects, one per
    outcome. We flatten into a list of holder rows tagged with the
    parent market's condition_id and the outcome's asset id.
    """
    page = http_get(f"/holders?market={condition_id}&limit={HOLDERS_LIMIT}")
    if not isinstance(page, list):
        return []
    flat: list[dict] = []
    for outcome_block in page:
        if not isinstance(outcome_block, dict):
            continue
        token = outcome_block.get("token")
        for h in outcome_block.get("holders", []) or []:
            if isinstance(h, dict):
                h2 = dict(h)
                h2["_token"] = token
                flat.append(h2)
    return flat


def holder_to_row(h: dict, condition_id: str, fetched_at: dt.datetime) -> tuple:
    return (
        condition_id,
        _fmt_str(h.get("asset") or h.get("_token")),
        _fmt_int(h.get("outcomeIndex")),
        _fmt_str(h.get("proxyWallet")).lower(),
        _fmt_float(h.get("amount")),
        _fmt_str(h.get("name")),
        _fmt_str(h.get("pseudonym")),
        _fmt_str(h.get("bio")),
        _fmt_str(h.get("profileImage")),
        _fmt_str(h.get("profileImageOptimized")),
        _fmt_bool(h.get("verified")),
        _fmt_bool(h.get("displayUsernamePublic")),
        fetched_at,
    )


def fetch_oi(condition_id: str) -> list[dict]:
    page = http_get(f"/oi?market={condition_id}")
    return list(page) if isinstance(page, list) else []


def oi_to_row(item: dict, fetched_at: dt.datetime) -> tuple:
    return (
        _fmt_str(item.get("market")),
        _fmt_float(item.get("value")),
        fetched_at,
    )


# ---------------------------------------------------------------------------
# Inserts
# ---------------------------------------------------------------------------
_INSERT_LOCK = threading.Lock()


def insert_trades(ch: ClickHouse, rows: Sequence[tuple]) -> None:
    if not rows:
        return
    with _INSERT_LOCK:
        ch.client.execute(
            f"""INSERT INTO {ch.database}.dataapi_trades (
                condition_id, tx_hash, trade_time, proxy_wallet, side, asset,
                size, price, outcome, outcome_index, title, slug, event_slug,
                icon, display_name, pseudonym, bio, profile_image,
                profile_image_optimized, fetched_at
            ) VALUES""",
            rows,
        )


def insert_holders(ch: ClickHouse, rows: Sequence[tuple]) -> None:
    if not rows:
        return
    with _INSERT_LOCK:
        ch.client.execute(
            f"""INSERT INTO {ch.database}.dataapi_holders (
                condition_id, asset, outcome_index, proxy_wallet, amount,
                display_name, pseudonym, bio, profile_image,
                profile_image_optimized, verified, display_username_public,
                fetched_at
            ) VALUES""",
            rows,
        )


def insert_oi(ch: ClickHouse, rows: Sequence[tuple]) -> None:
    if not rows:
        return
    with _INSERT_LOCK:
        ch.client.execute(
            f"""INSERT INTO {ch.database}.dataapi_oi (
                market, value, fetched_at
            ) VALUES""",
            rows,
        )


def mark_progress(ch: ClickHouse, endpoint: str, condition_id: str, row_count: int) -> None:
    with _INSERT_LOCK:
        ch.client.execute(
            f"""INSERT INTO {ch.database}.dataapi_progress
                (endpoint, condition_id, row_count, updated_at) VALUES""",
            [(endpoint, condition_id, row_count, dt.datetime.utcnow())],
        )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def list_condition_ids(ch: ClickHouse, limit: Optional[int] = None,
                        order_by_volume: bool = True) -> list[str]:
    order = "volume DESC" if order_by_volume else "market_id"
    sql = f"""
        SELECT DISTINCT condition_id
        FROM {ch.database}.markets_full FINAL
        WHERE condition_id != ''
        ORDER BY {order}
    """
    if limit:
        sql += f" LIMIT {limit}"
    rows = ch.client.execute(sql)
    return [r[0] for r in rows if r[0]]


def already_done(ch: ClickHouse, endpoint: str) -> set[str]:
    rows = ch.client.execute(
        f"""SELECT condition_id
            FROM {ch.database}.dataapi_progress FINAL
            WHERE endpoint = %(ep)s""",
        {"ep": endpoint},
    )
    return {r[0] for r in rows}


def crawl_endpoint(
    ch: ClickHouse, endpoint: str, condition_ids: Sequence[str],
    workers: int = 20, batch: int = 1000, log_every: int = 200,
) -> dict[str, int]:
    """Drive concurrent fetch+insert for a single endpoint. Returns
    a stats dict: {markets_done, rows_inserted, errors}."""
    fetcher: Callable[[str], list[dict]]
    row_builder: Callable[[dict, str, dt.datetime], tuple] | Callable[[dict, dt.datetime], tuple]
    inserter: Callable[[ClickHouse, Sequence[tuple]], None]

    if endpoint == "trades":
        fetcher = fetch_trades
        def builder(items, cid, fa): return [trade_to_row(t, fa) for t in items]
        inserter = insert_trades
    elif endpoint == "holders":
        fetcher = fetch_holders
        def builder(items, cid, fa): return [holder_to_row(h, cid, fa) for h in items]
        inserter = insert_holders
    elif endpoint == "oi":
        fetcher = fetch_oi
        def builder(items, cid, fa): return [oi_to_row(o, fa) for o in items]
        inserter = insert_oi
    else:
        raise ValueError(f"unknown endpoint: {endpoint}")

    stats = {"markets_done": 0, "rows_inserted": 0, "errors": 0}
    pending: list[tuple] = []

    def worker(cid: str) -> tuple[str, list[tuple], Optional[Exception]]:
        try:
            fa = dt.datetime.utcnow()
            items = fetcher(cid)
            rows = builder(items, cid, fa)
            return cid, rows, None
        except Exception as e:
            return cid, [], e

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, cid) for cid in condition_ids]
        for i, fut in enumerate(as_completed(futures), start=1):
            cid, rows, err = fut.result()
            if err is not None:
                stats["errors"] += 1
                if stats["errors"] <= 10:
                    log.warning("[%s] %s failed: %r", endpoint, cid[:12] + "...", err)
                # don't mark progress so it gets retried later
            else:
                pending.extend(rows)
                stats["markets_done"] += 1
                stats["rows_inserted"] += len(rows)
                # We mark progress per-market, but flush to CH in batches:
                if len(pending) >= batch:
                    inserter(ch, pending)
                    pending = []
                mark_progress(ch, endpoint, cid, len(rows))
            if i % log_every == 0:
                elapsed = time.time() - t0
                rps = i / elapsed if elapsed else 0
                eta = (len(condition_ids) - i) / rps if rps > 0 else 0
                log.info(
                    "[%s] progress %d/%d (%.1f%%) | rows=%d errors=%d | %.1f req/s | ETA %.1fm",
                    endpoint, i, len(condition_ids), 100*i/len(condition_ids),
                    stats["rows_inserted"], stats["errors"], rps, eta/60,
                )
    if pending:
        inserter(ch, pending)
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", choices=["trades", "holders", "oi", "all"],
                        default="oi")
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--batch", type=int, default=1000)
    parser.add_argument("--markets-limit", type=int, default=None,
                        help="Cap number of markets (smoke testing).")
    parser.add_argument("--no-resume", action="store_true",
                        help="Re-process all markets even if already in dataapi_progress.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    s = get_settings()
    ch = ClickHouse(
        host=s.CLICKHOUSE_HOST, port=s.CLICKHOUSE_PORT,
        user=s.CLICKHOUSE_USER, password=s.CLICKHOUSE_PASSWORD,
        database=s.CLICKHOUSE_DATABASE,
    )
    ensure_dataapi_schemas(ch)

    cids = list_condition_ids(ch, limit=args.markets_limit, order_by_volume=True)
    log.info("loaded %s condition_ids from markets_full (volume desc)", len(cids))

    endpoints = ["oi", "holders", "trades"] if args.endpoint == "all" else [args.endpoint]
    for ep in endpoints:
        if not args.no_resume:
            done = already_done(ch, ep)
            todo = [c for c in cids if c not in done]
            log.info("[%s] %s already done; %s remain", ep, len(done), len(todo))
        else:
            todo = cids
        if not todo:
            log.info("[%s] nothing to do", ep)
            continue

        stats = crawl_endpoint(
            ch, ep, todo, workers=args.workers, batch=args.batch,
        )
        log.info("[%s] DONE markets=%s rows=%s errors=%s",
                 ep, stats["markets_done"], stats["rows_inserted"], stats["errors"])


if __name__ == "__main__":
    main()
