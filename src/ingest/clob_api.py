"""
Crawl Polymarket CLOB API (https://clob.polymarket.com) into ClickHouse.

Endpoints crawled:
  /markets                  → polymetl.clob_markets         (full metadata)
  /prices-history           → polymetl.clob_prices_history  (hourly OHLC-style time series, t/p)
  /book                     → polymetl.clob_orderbook       (current orderbook snapshot)
  POST /midpoints,/spreads,
       /last-trades-prices  → polymetl.clob_quotes          (best bid/ask/mid quote)

Resume: per-(endpoint, key) progress in polymetl.clob_progress.

Usage:
    uv run python -m src.clob_api --endpoint markets         # ~10 min
    uv run python -m src.clob_api --endpoint prices_history --workers 30   # hours, the big one
    uv run python -m src.clob_api --endpoint orderbook       # only active tokens
    uv run python -m src.clob_api --endpoint quotes          # only active tokens
    uv run python -m src.clob_api --endpoint all             # markets → quotes → orderbook → prices_history
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
from typing import Any, Optional, Sequence

from ..pipeline.clickhouse import ClickHouse
from ..pipeline.config import get_settings


CLOB_BASE = "https://clob.polymarket.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Accept": "application/json,*/*",
    "Origin": "https://polymarket.com",
    "Referer": "https://polymarket.com/",
}

# /prices-history params: fidelity is in minutes; minimum 10.
# Polymarket's API rules (as of 2026-05-09) reject explicit startTs/endTs windows
# longer than ~1 day and rate-limit non-`interval=max` requests aggressively.
# Strategy: ask for `interval=max&fidelity=60` first (hourly, works for active
# markets). If that returns 0 points (closed/older markets get rate-restricted
# at hourly), fall back to `interval=max&fidelity=1440` (daily) which works
# universally. Track which fidelity actually produced rows for the audit trail.
PRICES_HISTORY_FIDELITY_PRIMARY = 60
PRICES_HISTORY_FIDELITY_FALLBACK = 1440

QUOTES_BATCH = 100  # tokens per batch POST call


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
def ensure_clob_schemas(ch: ClickHouse) -> None:
    db = ch.database

    ch.client.execute(f"""
        CREATE TABLE IF NOT EXISTS {db}.clob_markets (
            condition_id          String,
            question_id           String,
            question              String,
            description           String,
            market_slug           String,
            enable_order_book     UInt8,
            active                UInt8,
            closed                UInt8,
            archived              UInt8,
            accepting_orders      UInt8,
            accepting_order_timestamp Nullable(DateTime),
            minimum_order_size    Float64,
            minimum_tick_size     Float64,
            neg_risk              UInt8,
            neg_risk_market_id    String,
            neg_risk_request_id   String,
            end_date_iso          Nullable(DateTime),
            game_start_time       Nullable(DateTime),
            seconds_delay         UInt32,
            maker_base_fee        Int64,
            taker_base_fee        Int64,
            fpmm                  String,
            is_50_50_outcome      UInt8,
            notifications_enabled UInt8,
            icon                  String,
            image                 String,
            tags                  Array(String),
            tokens_json           String,
            rewards_min_size      Float64,
            rewards_max_spread    Float64,
            rewards_rates_json    String,
            raw_json              String,
            fetched_at            DateTime
        )
        ENGINE = ReplacingMergeTree(fetched_at)
        ORDER BY condition_id
        SETTINGS index_granularity = 8192
    """)

    # Time-series of (token, t, p). t is the hourly bucket from /prices-history.
    ch.client.execute(f"""
        CREATE TABLE IF NOT EXISTS {db}.clob_prices_history (
            token_id        String,
            t               DateTime,
            p               Float64,
            fidelity_min    UInt32,
            fetched_at      DateTime
        )
        ENGINE = ReplacingMergeTree(fetched_at)
        PARTITION BY toYYYYMM(t)
        ORDER BY (token_id, t)
        SETTINGS index_granularity = 8192
    """)

    # Orderbook snapshot. Keep history-friendly by including fetched_at in ORDER BY.
    ch.client.execute(f"""
        CREATE TABLE IF NOT EXISTS {db}.clob_orderbook (
            token_id        String,
            market          String,
            side            LowCardinality(String),
            price           Float64,
            size            Float64,
            book_timestamp  UInt64,
            book_hash       String,
            fetched_at      DateTime
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMMDD(fetched_at)
        ORDER BY (token_id, side, price, fetched_at)
        SETTINGS index_granularity = 8192
    """)

    # Quotes: best bid/ask/mid/spread/last trade per token
    ch.client.execute(f"""
        CREATE TABLE IF NOT EXISTS {db}.clob_quotes (
            token_id           String,
            midpoint           Float64,
            best_bid           Float64,
            best_ask           Float64,
            spread             Float64,
            last_trade_price   Float64,
            last_trade_side    LowCardinality(String),
            fetched_at         DateTime
        )
        ENGINE = ReplacingMergeTree(fetched_at)
        ORDER BY token_id
        SETTINGS index_granularity = 8192
    """)

    ch.client.execute(f"""
        CREATE TABLE IF NOT EXISTS {db}.clob_progress (
            endpoint     LowCardinality(String),
            key          String,
            row_count    UInt32,
            updated_at   DateTime
        )
        ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY (endpoint, key)
    """)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def http_get(path: str, timeout: float = 20.0, max_retries: int = 5) -> Any:
    url = CLOB_BASE + path
    last: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                last = e
                time.sleep(min(2 ** attempt + 0.5, 30))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(min(2 ** attempt + 0.5, 30))
    raise RuntimeError(f"GET {url} failed: {last!r}")


def http_post(path: str, body: Any, timeout: float = 20.0,
              max_retries: int = 5) -> Any:
    url = CLOB_BASE + path
    data = json.dumps(body).encode()
    last: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={**HEADERS, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                last = e
                time.sleep(min(2 ** attempt + 0.5, 30))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(min(2 ** attempt + 0.5, 30))
    raise RuntimeError(f"POST {url} failed: {last!r}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _S(v: Any) -> str:
    return "" if v is None else str(v)


def _F(v: Any) -> float:
    try: return float(v)
    except (TypeError, ValueError): return 0.0


def _I(v: Any) -> int:
    try: return int(float(v))
    except (TypeError, ValueError): return 0


def _B(v: Any) -> int:
    return 1 if bool(v) else 0


def _DT(v: Any) -> Optional[dt.datetime]:
    if not v:
        return None
    if isinstance(v, dt.datetime):
        return v.replace(tzinfo=None)
    if not isinstance(v, str):
        return None
    s = v.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        return None


def _J(v: Any) -> str:
    if v is None: return ""
    if isinstance(v, str): return v
    try: return json.dumps(v, ensure_ascii=False, default=str)
    except: return ""


# ---------------------------------------------------------------------------
# /markets
# ---------------------------------------------------------------------------
def market_to_row(m: dict, fetched_at: dt.datetime) -> tuple:
    rewards = m.get("rewards") or {}
    return (
        _S(m.get("condition_id")),
        _S(m.get("question_id")),
        _S(m.get("question")),
        _S(m.get("description")),
        _S(m.get("market_slug")),
        _B(m.get("enable_order_book")),
        _B(m.get("active")),
        _B(m.get("closed")),
        _B(m.get("archived")),
        _B(m.get("accepting_orders")),
        _DT(m.get("accepting_order_timestamp")),
        _F(m.get("minimum_order_size")),
        _F(m.get("minimum_tick_size")),
        _B(m.get("neg_risk")),
        _S(m.get("neg_risk_market_id")),
        _S(m.get("neg_risk_request_id")),
        _DT(m.get("end_date_iso")),
        _DT(m.get("game_start_time")),
        _I(m.get("seconds_delay")),
        _I(m.get("maker_base_fee")),
        _I(m.get("taker_base_fee")),
        _S(m.get("fpmm")),
        _B(m.get("is_50_50_outcome")),
        _B(m.get("notifications_enabled")),
        _S(m.get("icon")),
        _S(m.get("image")),
        [str(t) for t in (m.get("tags") or [])],
        _J(m.get("tokens")),
        _F(rewards.get("min_size")),
        _F(rewards.get("max_spread")),
        _J(rewards.get("rates")),
        _J(m),
        fetched_at,
    )


def insert_markets(ch: ClickHouse, rows: Sequence[tuple]) -> None:
    if not rows: return
    ch.client.execute(
        f"""INSERT INTO {ch.database}.clob_markets (
            condition_id, question_id, question, description, market_slug,
            enable_order_book, active, closed, archived, accepting_orders,
            accepting_order_timestamp, minimum_order_size, minimum_tick_size,
            neg_risk, neg_risk_market_id, neg_risk_request_id,
            end_date_iso, game_start_time, seconds_delay,
            maker_base_fee, taker_base_fee, fpmm, is_50_50_outcome,
            notifications_enabled, icon, image, tags, tokens_json,
            rewards_min_size, rewards_max_spread, rewards_rates_json,
            raw_json, fetched_at
        ) VALUES""",
        rows,
    )


def crawl_markets(ch: ClickHouse, page_size: int = 1000) -> int:
    cursor = ""
    total = 0
    pages = 0
    while True:
        path = f"/markets?next_cursor={urllib.parse.quote(cursor)}" if cursor else "/markets"
        obj = http_get(path)
        data = obj.get("data") or []
        if not data:
            break
        fa = dt.datetime.utcnow()
        rows = [market_to_row(m, fa) for m in data]
        insert_markets(ch, rows)
        total += len(rows)
        pages += 1
        log.info("clob_markets: page %d (+%d markets, total %d)", pages, len(rows), total)
        nxt = obj.get("next_cursor")
        if not nxt or nxt == "LTE=":
            break
        cursor = nxt
    log.info("clob_markets DONE: %d markets in %d pages", total, pages)
    return total


# ---------------------------------------------------------------------------
# /prices-history
# ---------------------------------------------------------------------------
def fetch_prices_history(token_id: str) -> tuple[list[dict], int]:
    """Return (points, fidelity_used). Tries hourly first; falls back to
    daily if hourly returns empty (typical for closed/old markets).

    The CLOB API silently returns [] (HTTP 200) when the requested
    resolution isn't available for the market — not an error, just empty."""
    path = (f"/prices-history?market={token_id}"
            f"&interval=max&fidelity={PRICES_HISTORY_FIDELITY_PRIMARY}")
    obj = http_get(path)
    pts = obj.get("history") or []
    if pts:
        return pts, PRICES_HISTORY_FIDELITY_PRIMARY

    path2 = (f"/prices-history?market={token_id}"
             f"&interval=max&fidelity={PRICES_HISTORY_FIDELITY_FALLBACK}")
    obj2 = http_get(path2)
    return obj2.get("history") or [], PRICES_HISTORY_FIDELITY_FALLBACK


def prices_history_to_rows(token_id: str, points: list[dict],
                            fa: dt.datetime, fidelity: int) -> list[tuple]:
    out = []
    for pt in points:
        ts = _I(pt.get("t"))
        if ts <= 0:
            continue
        try:
            t_dt = dt.datetime.utcfromtimestamp(ts)
        except (OSError, ValueError):
            continue
        out.append((token_id, t_dt, _F(pt.get("p")), fidelity, fa))
    return out


def insert_prices_history(ch: ClickHouse, rows: Sequence[tuple]) -> None:
    if not rows: return
    ch.client.execute(
        f"""INSERT INTO {ch.database}.clob_prices_history (
            token_id, t, p, fidelity_min, fetched_at
        ) VALUES""",
        rows,
    )


# ---------------------------------------------------------------------------
# /book (single GET — could be batched via POST /books, but simpler this way)
# ---------------------------------------------------------------------------
def fetch_book(token_id: str) -> Optional[dict]:
    try:
        return http_get(f"/book?token_id={token_id}")
    except urllib.error.HTTPError as e:
        if e.code == 404:  # closed market, no book
            return None
        raise


def book_to_rows(book: dict, fa: dt.datetime) -> list[tuple]:
    if not book:
        return []
    token_id = _S(book.get("asset_id") or book.get("token_id"))
    market = _S(book.get("market"))
    bts = _I(book.get("timestamp"))
    bhash = _S(book.get("hash"))
    out = []
    for side_key, side_label in [("bids", "bid"), ("asks", "ask")]:
        for level in book.get(side_key) or []:
            out.append((
                token_id, market, side_label,
                _F(level.get("price")), _F(level.get("size")),
                bts, bhash, fa,
            ))
    return out


def insert_orderbook(ch: ClickHouse, rows: Sequence[tuple]) -> None:
    if not rows: return
    ch.client.execute(
        f"""INSERT INTO {ch.database}.clob_orderbook (
            token_id, market, side, price, size,
            book_timestamp, book_hash, fetched_at
        ) VALUES""",
        rows,
    )


# ---------------------------------------------------------------------------
# Quotes via batch POSTs
# ---------------------------------------------------------------------------
def fetch_quotes_batch(token_ids: list[str]) -> dict[str, dict]:
    """For a batch of tokens, gather midpoint, spread, prices (best bid/ask),
    last-trade-price into a single per-token dict.

    POST /midpoints      → {"<tokid>": "0.5", ...}
    POST /spreads        → {"<tokid>": "0.02", ...}
    POST /prices         → {"<tokid>": {"BUY":"0.51","SELL":"0.49"}, ...}
    POST /last-trades-prices → [{"price":"0.50","side":"SELL","token_id":"..."}, ...]
    """
    mid_body = [{"token_id": t} for t in token_ids]
    spr_body = [{"token_id": t} for t in token_ids]
    prc_body = [{"token_id": t, "side": s}
                for t in token_ids for s in ("BUY", "SELL")]
    lt_body  = [{"token_id": t} for t in token_ids]

    mid = http_post("/midpoints", mid_body) or {}
    spr = http_post("/spreads", spr_body) or {}
    prc = http_post("/prices", prc_body) or {}
    lt  = http_post("/last-trades-prices", lt_body) or []

    lt_map: dict[str, dict] = {}
    if isinstance(lt, list):
        for item in lt:
            if isinstance(item, dict):
                tid = _S(item.get("token_id"))
                lt_map[tid] = item

    out: dict[str, dict] = {}
    for tid in token_ids:
        prc_inner = prc.get(tid) if isinstance(prc, dict) else {}
        if not isinstance(prc_inner, dict): prc_inner = {}
        out[tid] = {
            "midpoint": _F(mid.get(tid)),
            "spread":   _F(spr.get(tid)),
            "best_buy":  _F(prc_inner.get("BUY")),
            "best_sell": _F(prc_inner.get("SELL")),
            "last_trade_price": _F((lt_map.get(tid) or {}).get("price")),
            "last_trade_side":  _S((lt_map.get(tid) or {}).get("side")),
        }
    return out


def quotes_to_rows(per_token: dict[str, dict], fa: dt.datetime) -> list[tuple]:
    out = []
    for tid, q in per_token.items():
        # In CLOB convention: best_bid = best BUY price, best_ask = best SELL price.
        best_bid = q["best_buy"]
        best_ask = q["best_sell"]
        out.append((
            tid,
            q["midpoint"],
            best_bid, best_ask,
            q["spread"],
            q["last_trade_price"], q["last_trade_side"],
            fa,
        ))
    return out


def insert_quotes(ch: ClickHouse, rows: Sequence[tuple]) -> None:
    if not rows: return
    ch.client.execute(
        f"""INSERT INTO {ch.database}.clob_quotes (
            token_id, midpoint, best_bid, best_ask, spread,
            last_trade_price, last_trade_side, fetched_at
        ) VALUES""",
        rows,
    )


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------
_LOCK = threading.Lock()


def mark_progress(ch: ClickHouse, endpoint: str, key: str, row_count: int) -> None:
    with _LOCK:
        ch.client.execute(
            f"""INSERT INTO {ch.database}.clob_progress
                (endpoint, key, row_count, updated_at) VALUES""",
            [(endpoint, key, row_count, dt.datetime.utcnow())],
        )


def already_done(ch: ClickHouse, endpoint: str) -> set[str]:
    rows = ch.client.execute(
        f"""SELECT DISTINCT key FROM {ch.database}.clob_progress FINAL
            WHERE endpoint = %(ep)s""",
        {"ep": endpoint},
    )
    return {r[0] for r in rows}


def list_token_ids(ch: ClickHouse, only_active: bool = False) -> list[str]:
    if only_active:
        sql = f"""
            SELECT DISTINCT JSONExtractString(token, 'token_id') AS tid
            FROM {ch.database}.clob_markets FINAL
            ARRAY JOIN JSONExtractArrayRaw(tokens_json) AS token
            WHERE accepting_orders = 1 AND tid != ''
        """
    else:
        sql = f"""
            SELECT DISTINCT JSONExtractString(token, 'token_id') AS tid
            FROM {ch.database}.clob_markets FINAL
            ARRAY JOIN JSONExtractArrayRaw(tokens_json) AS token
            WHERE tid != ''
        """
    return [r[0] for r in ch.client.execute(sql)]


# ---------------------------------------------------------------------------
# Concurrent crawl helpers
# ---------------------------------------------------------------------------
def crawl_prices_history(ch: ClickHouse, token_ids: list[str], workers: int = 30,
                         batch_rows: int = 5000, log_every: int = 200) -> dict:
    stats = {"tokens_done": 0, "rows": 0, "errors": 0}
    pending: list[tuple] = []

    def worker(tid: str):
        try:
            fa = dt.datetime.utcnow()
            pts, fid = fetch_prices_history(tid)
            return tid, prices_history_to_rows(tid, pts, fa, fid), None
        except Exception as e:
            return tid, [], e

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, t) for t in token_ids]
        for i, fut in enumerate(as_completed(futures), 1):
            tid, rows, err = fut.result()
            if err is not None:
                stats["errors"] += 1
                if stats["errors"] <= 10:
                    log.warning("[prices_history] %s: %r", tid[:14] + "...", err)
            else:
                with _LOCK:
                    pending.extend(rows)
                stats["tokens_done"] += 1
                stats["rows"] += len(rows)
                if len(pending) >= batch_rows:
                    with _LOCK:
                        flush, pending = pending, []
                    insert_prices_history(ch, flush)
                mark_progress(ch, "prices_history", tid, len(rows))
            if i % log_every == 0:
                el = time.time() - t0
                rps = i / el if el else 0
                eta = (len(token_ids) - i) / rps if rps > 0 else 0
                log.info("[prices_history] %d/%d (%.1f%%) | rows=%d errors=%d | %.1f rps | ETA %.1fm",
                         i, len(token_ids), 100*i/len(token_ids),
                         stats["rows"], stats["errors"], rps, eta/60)
    if pending:
        insert_prices_history(ch, pending)
    return stats


def crawl_orderbook(ch: ClickHouse, token_ids: list[str], workers: int = 30,
                    batch_rows: int = 5000, log_every: int = 200) -> dict:
    stats = {"tokens_done": 0, "rows": 0, "errors": 0}
    pending: list[tuple] = []

    def worker(tid: str):
        try:
            fa = dt.datetime.utcnow()
            book = fetch_book(tid)
            return tid, book_to_rows(book, fa) if book else [], None
        except Exception as e:
            return tid, [], e

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, t) for t in token_ids]
        for i, fut in enumerate(as_completed(futures), 1):
            tid, rows, err = fut.result()
            if err is not None:
                stats["errors"] += 1
            else:
                with _LOCK:
                    pending.extend(rows)
                stats["tokens_done"] += 1
                stats["rows"] += len(rows)
                if len(pending) >= batch_rows:
                    with _LOCK:
                        flush, pending = pending, []
                    insert_orderbook(ch, flush)
                mark_progress(ch, "orderbook", tid, len(rows))
            if i % log_every == 0:
                el = time.time() - t0
                rps = i / el if el else 0
                eta = (len(token_ids) - i) / rps if rps > 0 else 0
                log.info("[orderbook] %d/%d (%.1f%%) | rows=%d errors=%d | %.1f rps | ETA %.1fm",
                         i, len(token_ids), 100*i/len(token_ids),
                         stats["rows"], stats["errors"], rps, eta/60)
    if pending:
        insert_orderbook(ch, pending)
    return stats


def crawl_quotes(ch: ClickHouse, token_ids: list[str], batch_size: int = QUOTES_BATCH,
                 log_every: int = 50) -> dict:
    """Sequential batched quotes — POST endpoints accept arrays so we already
    parallelize within each call. No need for thread pool."""
    stats = {"tokens_done": 0, "rows": 0, "errors": 0}
    n_batches = (len(token_ids) + batch_size - 1) // batch_size
    t0 = time.time()
    for i in range(0, len(token_ids), batch_size):
        chunk = token_ids[i:i+batch_size]
        try:
            qmap = fetch_quotes_batch(chunk)
            fa = dt.datetime.utcnow()
            rows = quotes_to_rows(qmap, fa)
            insert_quotes(ch, rows)
            stats["tokens_done"] += len(chunk)
            stats["rows"] += len(rows)
            for tid in chunk:
                mark_progress(ch, "quotes", tid, 1)
        except Exception as e:
            stats["errors"] += len(chunk)
            log.warning("[quotes] batch %d failed: %r", i // batch_size, e)
        if (i // batch_size + 1) % log_every == 0:
            el = time.time() - t0
            done_batches = i // batch_size + 1
            rps = stats["tokens_done"] / el if el else 0
            eta = (len(token_ids) - stats["tokens_done"]) / rps if rps > 0 else 0
            log.info("[quotes] batch %d/%d  tokens=%d  errors=%d  %.1f tok/s  ETA %.1fm",
                     done_batches, n_batches, stats["tokens_done"],
                     stats["errors"], rps, eta/60)
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint",
                        choices=["markets", "prices_history", "orderbook", "quotes", "all"],
                        default="markets")
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--quotes-batch", type=int, default=QUOTES_BATCH)
    parser.add_argument("--tokens-limit", type=int, default=None,
                        help="Cap number of tokens (smoke testing).")
    parser.add_argument("--no-resume", action="store_true",
                        help="Re-process keys even if in clob_progress.")
    parser.add_argument("--only-active", action="store_true",
                        help="For orderbook/quotes: limit to accepting_orders=1 tokens.")
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
    ensure_clob_schemas(ch)

    endpoints = (["markets", "quotes", "orderbook", "prices_history"]
                 if args.endpoint == "all" else [args.endpoint])

    for ep in endpoints:
        if ep == "markets":
            crawl_markets(ch)
            continue

        # Endpoints that need a token list sourced from clob_markets:
        all_tokens = list_token_ids(ch, only_active=(ep in ("orderbook", "quotes")
                                                      or args.only_active))
        if args.tokens_limit:
            all_tokens = all_tokens[: args.tokens_limit]

        if not args.no_resume:
            done = already_done(ch, ep)
            todo = [t for t in all_tokens if t not in done]
            log.info("[%s] %d already done; %d remain (of %d)",
                     ep, len(done), len(todo), len(all_tokens))
        else:
            todo = all_tokens
            log.info("[%s] no-resume: re-processing all %d tokens", ep, len(todo))

        if not todo:
            log.info("[%s] nothing to do", ep)
            continue

        if ep == "prices_history":
            stats = crawl_prices_history(ch, todo, workers=args.workers)
        elif ep == "orderbook":
            stats = crawl_orderbook(ch, todo, workers=args.workers)
        elif ep == "quotes":
            stats = crawl_quotes(ch, todo, batch_size=args.quotes_batch)
        log.info("[%s] DONE tokens=%d rows=%d errors=%d",
                 ep, stats["tokens_done"], stats["rows"], stats["errors"])


if __name__ == "__main__":
    main()
