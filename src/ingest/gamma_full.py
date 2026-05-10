"""
Full-fidelity Gamma markets puller — captures every field the Gamma /markets
endpoint returns (~125 keys observed on 2026-05-08), into a new ClickHouse
table polymetl.markets_full.

Design choices:
- Scalars (string/bool/int/float/datetime) are stored in typed columns.
- JSON-encoded array strings (outcomes, clobTokenIds, outcomePrices,
  umaResolutionStatuses) are parsed into native Array columns.
- Nested objects/arrays of dicts (events, clobRewards, feeSchedule, tags)
  are kept as JSON String columns — analytical access via JSONExtract*().
- A `raw_json` column stores the full original API response so future
  field additions never require a re-pull from Gamma.
- Engine: ReplacingMergeTree(fetched_at) ORDER BY market_id — same idempotent
  semantics as the original markets table; query with FINAL to dedupe.

Usage:
    uv run python -m src.gamma_full --closed all
    uv run python -m src.gamma_full --closed false
    uv run python -m src.gamma_full --closed true
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from typing import Any, Optional, Sequence

import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator

from ..pipeline.clickhouse import ClickHouse
from ..pipeline.config import get_settings


log = logging.getLogger(__name__)


# Helpers (v7: inlined from the deleted src/gamma.py — gamma_full now
# subsumes the legacy thin gamma puller).
GAMMA_BASE = "https://gamma-api.polymarket.com"
USER_AGENT = "polymetl-gamma/0.2"


def fetch_markets_page(
    limit: int = 500, offset: int = 0, closed: Optional[bool] = None,
    base: str = GAMMA_BASE, timeout: float = 30.0,
) -> list[dict]:
    params: dict = {"limit": limit, "offset": offset}
    if closed is not None:
        params["closed"] = "true" if closed else "false"
    url = f"{base}/markets?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    return list(payload) if payload else []


def iter_all_markets(
    page_size: int = 500, closed: Optional[bool] = None,
    sleep: float = 0.2, fetch_fn=fetch_markets_page,
) -> Iterator[dict]:
    offset = 0
    while True:
        try:
            page = fetch_fn(limit=page_size, offset=offset, closed=closed)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 422):
                log.warning(
                    "Gamma rejected offset=%s with HTTP %s; stopping",
                    offset, exc.code,
                )
                return
            raise
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


# (column_name, source_key_in_api, clickhouse_type, parser_kind)
# parser_kind ∈ {"str","bool","int","float","datetime","arr_str","arr_float","json"}
FIELDS: list[tuple[str, str, str, str]] = [
    # ---------- Identity ----------
    ("market_id",                "id",                          "String",            "str"),
    ("slug",                     "slug",                        "String",            "str"),
    ("question",                 "question",                    "String",            "str"),
    ("description",              "description",                 "String",            "str"),
    ("question_id",              "questionID",                  "String",            "str"),
    ("condition_id",             "conditionId",                 "String",            "str"),
    ("market_maker_address",     "marketMakerAddress",          "String",            "str"),
    ("creator",                  "creator",                     "String",            "str"),
    ("submitted_by",             "submitted_by",                "String",            "str"),
    ("category",                 "category",                    "String",            "str"),
    ("subcategory",              "subcategory",                 "String",            "str"),
    ("category_mailchimp_tag",   "categoryMailchimpTag",        "String",            "str"),
    ("mailchimp_tag",            "mailchimpTag",                "String",            "str"),
    ("market_type",              "marketType",                  "String",            "str"),
    ("sports_market_type",       "sportsMarketType",            "String",            "str"),
    ("format_type",              "formatType",                  "String",            "str"),
    ("denomination_token",       "denominationToken",           "String",            "str"),
    ("game_id",                  "gameId",                      "String",            "str"),
    ("group_item_title",         "groupItemTitle",              "String",            "str"),
    ("group_item_threshold",     "groupItemThreshold",          "String",            "str"),

    # ---------- Media ----------
    ("icon",                     "icon",                        "String",            "str"),
    ("image",                    "image",                       "String",            "str"),
    ("twitter_card_image",       "twitterCardImage",            "String",            "str"),
    ("sponsor_image",            "sponsorImage",                "String",            "str"),
    ("series_color",             "seriesColor",                 "String",            "str"),

    # ---------- Outcomes / resolution ----------
    ("outcomes",                 "outcomes",                    "Array(String)",     "arr_str"),
    ("clob_token_ids",           "clobTokenIds",                "Array(String)",     "arr_str"),
    ("outcome_prices",           "outcomePrices",               "Array(Float64)",    "arr_float"),
    ("uma_resolution_statuses",  "umaResolutionStatuses",       "Array(String)",     "arr_str"),
    ("uma_resolution_status",    "umaResolutionStatus",         "String",            "str"),
    ("resolved_by",              "resolvedBy",                  "String",            "str"),
    ("resolution_source",        "resolutionSource",            "String",            "str"),
    ("automatically_resolved",   "automaticallyResolved",       "UInt8",             "bool"),
    ("lower_bound",              "lowerBound",                  "String",            "str"),
    ("upper_bound",              "upperBound",                  "String",            "str"),
    ("line",                     "line",                        "Float64",           "float"),

    # ---------- Order book / pricing ----------
    ("last_trade_price",         "lastTradePrice",              "Float64",           "float"),
    ("best_bid",                 "bestBid",                     "Float64",           "float"),
    ("best_ask",                 "bestAsk",                     "Float64",           "float"),
    ("spread",                   "spread",                      "Float64",           "float"),
    ("order_min_size",           "orderMinSize",                "UInt32",            "int"),
    ("order_price_min_tick_size","orderPriceMinTickSize",       "Float64",           "float"),
    ("rewards_min_size",         "rewardsMinSize",              "UInt32",            "int"),
    ("rewards_max_spread",       "rewardsMaxSpread",            "Float64",           "float"),
    ("competitive",              "competitive",                 "Float64",           "float"),

    # ---------- Volume ----------
    ("volume",                   "volume",                      "Float64",           "float"),
    ("volume_clob",              "volumeClob",                  "Float64",           "float"),
    ("volume_num",               "volumeNum",                   "Float64",           "float"),
    ("volume_24hr",              "volume24hr",                  "Float64",           "float"),
    ("volume_1wk",               "volume1wk",                   "Float64",           "float"),
    ("volume_1mo",               "volume1mo",                   "Float64",           "float"),
    ("volume_1yr",               "volume1yr",                   "Float64",           "float"),
    ("volume_24hr_clob",         "volume24hrClob",              "Float64",           "float"),
    ("volume_1wk_clob",          "volume1wkClob",               "Float64",           "float"),
    ("volume_1mo_clob",          "volume1moClob",               "Float64",           "float"),
    ("volume_1yr_clob",          "volume1yrClob",               "Float64",           "float"),
    ("volume_1wk_amm",           "volume1wkAmm",                "Float64",           "float"),
    ("volume_1mo_amm",           "volume1moAmm",                "Float64",           "float"),
    ("volume_1yr_amm",           "volume1yrAmm",                "Float64",           "float"),

    # ---------- Liquidity ----------
    ("liquidity",                "liquidity",                   "Float64",           "float"),
    ("liquidity_clob",           "liquidityClob",               "Float64",           "float"),
    ("liquidity_amm",            "liquidityAmm",                "Float64",           "float"),
    ("liquidity_num",            "liquidityNum",                "Float64",           "float"),

    # ---------- Price changes ----------
    ("one_hour_price_change",    "oneHourPriceChange",          "Float64",           "float"),
    ("one_day_price_change",     "oneDayPriceChange",           "Float64",           "float"),
    ("one_week_price_change",    "oneWeekPriceChange",          "Float64",           "float"),
    ("one_month_price_change",   "oneMonthPriceChange",         "Float64",           "float"),
    ("one_year_price_change",    "oneYearPriceChange",          "Float64",           "float"),

    # ---------- Timestamps ----------
    ("start_date",               "startDate",                   "Nullable(DateTime)","datetime"),
    ("start_date_iso",           "startDateIso",                "Nullable(DateTime)","datetime"),
    ("end_date",                 "endDate",                     "Nullable(DateTime)","datetime"),
    ("end_date_iso",             "endDateIso",                  "Nullable(DateTime)","datetime"),
    ("uma_end_date",             "umaEndDate",                  "Nullable(DateTime)","datetime"),
    ("closed_time",              "closedTime",                  "Nullable(DateTime)","datetime"),
    ("created_at",               "createdAt",                   "Nullable(DateTime)","datetime"),
    ("updated_at",               "updatedAt",                   "Nullable(DateTime)","datetime"),
    ("accepting_orders_timestamp","acceptingOrdersTimestamp",   "Nullable(DateTime)","datetime"),
    ("deploying_timestamp",      "deployingTimestamp",          "Nullable(DateTime)","datetime"),
    ("game_start_time",          "gameStartTime",               "Nullable(DateTime)","datetime"),

    # ---------- Status flags ----------
    ("active",                   "active",                      "UInt8",             "bool"),
    ("closed",                   "closed",                      "UInt8",             "bool"),
    ("archived",                 "archived",                    "UInt8",             "bool"),
    ("restricted",               "restricted",                  "UInt8",             "bool"),
    ("enable_order_book",        "enableOrderBook",             "UInt8",             "bool"),
    ("accepting_orders",         "acceptingOrders",             "UInt8",             "bool"),
    ("funded",                   "funded",                      "UInt8",             "bool"),
    ("approved",                 "approved",                    "UInt8",             "bool"),
    ("ready",                    "ready",                       "UInt8",             "bool"),
    ("deploying",                "deploying",                   "UInt8",             "bool"),
    ("automatically_active",     "automaticallyActive",         "UInt8",             "bool"),
    ("pending_deployment",       "pendingDeployment",           "UInt8",             "bool"),
    ("manual_activation",        "manualActivation",            "UInt8",             "bool"),
    ("clear_book_on_start",      "clearBookOnStart",            "UInt8",             "bool"),
    ("cyom",                     "cyom",                        "UInt8",             "bool"),
    ("featured",                 "featured",                    "UInt8",             "bool"),
    ("fees_enabled",             "feesEnabled",                 "UInt8",             "bool"),
    ("fpmm_live",                "fpmmLive",                    "UInt8",             "bool"),
    ("has_reviewed_dates",       "hasReviewedDates",            "UInt8",             "bool"),
    ("holding_rewards_enabled",  "holdingRewardsEnabled",       "UInt8",             "bool"),
    ("is_new",                   "new",                         "UInt8",             "bool"),
    ("notifications_enabled",    "notificationsEnabled",        "UInt8",             "bool"),
    ("pager_duty_notification_enabled","pagerDutyNotificationEnabled","UInt8",       "bool"),
    ("ready_for_cron",           "readyForCron",                "UInt8",             "bool"),
    ("requires_translation",     "requiresTranslation",         "UInt8",             "bool"),
    ("rfq_enabled",              "rfqEnabled",                  "UInt8",             "bool"),
    ("sent_discord",             "sentDiscord",                 "UInt8",             "bool"),
    ("show_gmp_outcome",         "showGmpOutcome",              "UInt8",             "bool"),
    ("show_gmp_series",          "showGmpSeries",               "UInt8",             "bool"),
    ("wide_format",              "wideFormat",                  "UInt8",             "bool"),
    ("neg_risk",                 "negRisk",                     "UInt8",             "bool"),
    ("neg_risk_other",           "negRiskOther",                "UInt8",             "bool"),

    # ---------- Fees ----------
    ("fee",                      "fee",                         "String",            "str"),
    ("fee_type",                 "feeType",                     "String",            "str"),
    ("maker_base_fee",           "makerBaseFee",                "UInt32",            "int"),
    ("taker_base_fee",           "takerBaseFee",                "UInt32",            "int"),
    ("fee_schedule_json",        "feeSchedule",                 "String",            "json"),

    # ---------- UMA / arbitration ----------
    ("uma_bond",                 "umaBond",                     "String",            "str"),
    ("uma_reward",               "umaReward",                   "String",            "str"),
    ("custom_liveness",          "customLiveness",              "Int64",             "int"),
    ("neg_risk_market_id",       "negRiskMarketID",             "String",            "str"),
    ("neg_risk_request_id",      "negRiskRequestID",            "String",            "str"),

    # ---------- Misc ----------
    ("seconds_delay",            "secondsDelay",                "Int64",             "int"),
    ("updated_by",               "updatedBy",                   "Int64",             "int"),

    # ---------- Nested (JSON) ----------
    ("events_json",              "events",                      "String",            "json"),
    ("clob_rewards_json",        "clobRewards",                 "String",            "json"),
    ("tags_json",                "tags",                        "String",            "json"),
]

# Final two columns are bookkeeping, not from API:
EXTRA_COLS = [
    ("raw_json",   "String"),    # full original API response (for future field recovery)
    ("fetched_at", "DateTime"),  # ingest timestamp; doubles as ReplacingMergeTree version
]


def _parse_bool(v: Any) -> int:
    return 1 if bool(v) else 0


def _parse_int(v: Any) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _parse_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def _parse_arr_str(v: Any) -> list[str]:
    return [str(x) for x in _parse_json_array(v)]


def _parse_arr_float(v: Any) -> list[float]:
    return [_to_float(x) for x in _parse_json_array(v)]


def _parse_json_blob(v: Any) -> str:
    """Return v serialized as JSON (or '' if absent)."""
    if v is None:
        return ""
    if isinstance(v, str):
        # Already a JSON string — return as-is
        return v
    try:
        return json.dumps(v, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return ""


PARSERS = {
    "str":       _parse_str,
    "bool":      _parse_bool,
    "int":       _parse_int,
    "float":     _to_float,
    "datetime":  _parse_datetime,
    "arr_str":   _parse_arr_str,
    "arr_float": _parse_arr_float,
    "json":      _parse_json_blob,
}


def ensure_markets_full_schema(ch: ClickHouse) -> None:
    cols_sql = ",\n                ".join(
        f"{name} {ctype}" for name, _src, ctype, _kind in FIELDS
    ) + ",\n                " + ",\n                ".join(
        f"{name} {ctype}" for name, ctype in EXTRA_COLS
    )
    ch.client.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {ch.database}.markets_full (
            {cols_sql}
        )
        ENGINE = ReplacingMergeTree(fetched_at)
        ORDER BY market_id
        SETTINGS index_granularity = 8192
        """
    )


def market_to_full_row(m: dict, fetched_at: Optional[dt.datetime] = None) -> tuple:
    fetched_at = fetched_at or dt.datetime.utcnow()
    out: list[Any] = []
    for _name, src_key, _ctype, kind in FIELDS:
        out.append(PARSERS[kind](m.get(src_key)))
    out.append(json.dumps(m, ensure_ascii=False, default=str))  # raw_json
    out.append(fetched_at)
    return tuple(out)


def insert_markets_full(ch: ClickHouse, rows: Sequence[tuple]) -> None:
    if not rows:
        return
    col_names = [name for name, _src, _ctype, _kind in FIELDS] + [name for name, _ in EXTRA_COLS]
    cols_sql = ", ".join(col_names)
    ch.client.execute(
        f"INSERT INTO {ch.database}.markets_full ({cols_sql}) VALUES",
        rows,
    )


def run(
    closed: Optional[bool] = None,
    page_size: int = 500,
    batch_size: int = 1000,
    ch: Optional[ClickHouse] = None,
) -> int:
    if ch is None:
        s = get_settings()
        ch = ClickHouse(
            host=s.CLICKHOUSE_HOST, port=s.CLICKHOUSE_PORT,
            user=s.CLICKHOUSE_USER, password=s.CLICKHOUSE_PASSWORD,
            database=s.CLICKHOUSE_DATABASE,
        )
    ensure_markets_full_schema(ch)

    buffer: list[tuple] = []
    total = 0
    for m in iter_all_markets(page_size=page_size, closed=closed):
        buffer.append(market_to_full_row(m))
        if len(buffer) >= batch_size:
            insert_markets_full(ch, buffer)
            total += len(buffer)
            log.info("inserted %s markets_full (total %s)", len(buffer), total)
            buffer = []
    if buffer:
        insert_markets_full(ch, buffer)
        total += len(buffer)
    log.info("done; total markets_full inserted: %s", total)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closed", choices=["true", "false", "all"], default="all")
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
