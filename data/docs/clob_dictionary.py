"""
Generate ~/Desktop/polymetl_clob_dictionary.pdf — data dictionary for the
five CLOB ClickHouse tables:

  - polymetl.clob_markets         (full CLOB market metadata)
  - polymetl.clob_quotes          (current quote per outcome token: bid/ask/mid/spread)
  - polymetl.clob_orderbook       (current orderbook snapshot, all levels)
  - polymetl.clob_prices_history  (historical price time series, hourly fidelity)
  - polymetl.clob_progress        (per-(endpoint, key) crawl bookkeeping)

Each column row shows: column name, ClickHouse type, source CLOB JSON
field, computed fill-rate (% non-empty), Chinese description.

Usage:
    uv run python scripts/build_clob_dictionary_pdf.py
    uv run python scripts/build_clob_dictionary_pdf.py --out ~/Desktop/foo.pdf
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clickhouse_driver import Client
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


CJK = "STSong-Light"
MONO = "Courier"


TABLE_DEFS: dict[str, dict] = {
    "clob_markets": {
        "title": "polymetl.clob_markets  —  CLOB 市场元数据",
        "intro":
            "对 /markets 端点做 cursor 分页抓取（每页 1,000 行）。"
            "CLOB 暴露的市场数（约 1.07M）远多于 Gamma（146k），"
            "因为它包含 NegRisk 拆分子市场、归档/测试市场、以及 Gamma UI 不展示的"
            "历史市场。每行对应一个 conditionId，含 30+ 字段及完整 raw_json。"
            "ReplacingMergeTree(fetched_at) ORDER BY condition_id。",
        "endpoint": "GET /markets?next_cursor=…",
        "engine":   "ReplacingMergeTree(fetched_at) ORDER BY condition_id",
        "cols": [
            ("condition_id",            "String",            "condition_id",             "市场 conditionId（66 字符 hex），与 markets_full / dataapi_* 可 JOIN。"),
            ("question_id",             "String",            "question_id",              "UMA 问题 ID（用于仲裁追溯）。"),
            ("question",                "String",            "question",                 "题目原文。"),
            ("description",             "String",            "description",              "解析规则与背景说明。"),
            ("market_slug",             "String",            "market_slug",              "URL slug。"),
            ("enable_order_book",       "UInt8",             "enable_order_book",        "1=启用 CLOB 订单簿；0=仅 AMM 或未启用。"),
            ("active",                  "UInt8",             "active",                   "1=平台可见。"),
            ("closed",                  "UInt8",             "closed",                   "1=已结算。"),
            ("archived",                "UInt8",             "archived",                 "1=已归档（不在主页展示）。"),
            ("accepting_orders",        "UInt8",             "accepting_orders",         "1=当前可下单（quotes/orderbook 仅取这部分）。"),
            ("accepting_order_timestamp","Nullable(DateTime)","accepting_order_timestamp","开始接受订单的时刻。"),
            ("minimum_order_size",      "Float64",           "minimum_order_size",       "下单最小份额。"),
            ("minimum_tick_size",       "Float64",           "minimum_tick_size",        "价格最小步进（如 0.001 / 0.01 USDC/share）。"),
            ("neg_risk",                "UInt8",             "neg_risk",                 "1=属于 NegRisk 多结果聚合组。"),
            ("neg_risk_market_id",      "String",            "neg_risk_market_id",       "NegRisk 父 market 的 ID。"),
            ("neg_risk_request_id",     "String",            "neg_risk_request_id",      "NegRisk 解析请求 ID。"),
            ("end_date_iso",            "Nullable(DateTime)","end_date_iso",             "市场到期时间（UTC）。"),
            ("game_start_time",         "Nullable(DateTime)","game_start_time",          "体育市场赛事开赛时间。"),
            ("seconds_delay",           "UInt32",            "seconds_delay",            "数据延迟（秒）。"),
            ("maker_base_fee",          "Int64",             "maker_base_fee",           "做市方基础费率（基点）。"),
            ("taker_base_fee",          "Int64",             "taker_base_fee",           "吃单方基础费率（基点）。"),
            ("fpmm",                    "String",            "fpmm",                     "旧 FPMM (AMM) 合约地址；仅 AMM 时代市场非空。"),
            ("is_50_50_outcome",        "UInt8",             "is_50_50_outcome",         "1=平局退款标记（结算后 outcome_prices=[0.5,0.5]）。"),
            ("notifications_enabled",   "UInt8",             "notifications_enabled",    "1=启用市场动态推送（运维标志）。"),
            ("icon",                    "String",            "icon",                     "图标 URL。"),
            ("image",                   "String",            "image",                    "主图 URL。"),
            ("tags",                    "Array(String)",     "tags",                     "市场标签数组（如 ['All']）。"),
            ("tokens_json",             "String",            "tokens",                   "outcome token 数组（JSON）；元素含 token_id / outcome / price / winner。"),
            ("rewards_min_size",        "Float64",           "rewards.min_size",         "做市奖励要求的最小订单规模。"),
            ("rewards_max_spread",      "Float64",           "rewards.max_spread",       "奖励允许的最大 spread。"),
            ("rewards_rates_json",      "String",            "rewards.rates",            "奖励档位明细（JSON，多档位结构）。"),
            ("raw_json",                "String",            "(整对象)",                  "完整原始 API 响应；新字段日后通过 JSONExtract 恢复。"),
            ("fetched_at",              "DateTime",          "(本地)",                    "抓取时间戳。"),
        ],
    },

    "clob_quotes": {
        "title": "polymetl.clob_quotes  —  当前 token 报价（中价/价差/最优买卖/最近成交）",
        "intro":
            "对每个 accepting_orders=true 的 outcome token 调用 4 个批量 POST 端点："
            "/midpoints、/spreads、/prices、/last-trades-prices，合并为一行。"
            "ReplacingMergeTree(fetched_at) ORDER BY token_id —— 重新抓取时按 fetched_at 保留最新。"
            "想做时间序列就反复跑，每次会 append 新版本。",
        "endpoint": "POST /midpoints  POST /spreads  POST /prices  POST /last-trades-prices",
        "engine":   "ReplacingMergeTree(fetched_at) ORDER BY token_id",
        "cols": [
            ("token_id",          "String",                  "token_id",       "outcome token ID（uint256 字符串）。"),
            ("midpoint",          "Float64",                 "midpoints[*]",   "买卖中价。"),
            ("best_bid",          "Float64",                 "prices[*].BUY",  "当前最优买价（CLOB best bid）。"),
            ("best_ask",          "Float64",                 "prices[*].SELL", "当前最优卖价。"),
            ("spread",            "Float64",                 "spreads[*]",     "best_ask − best_bid。"),
            ("last_trade_price",  "Float64",                 "last-trades-prices[*].price", "最近一笔成交价。"),
            ("last_trade_side",   "LowCardinality(String)",  "last-trades-prices[*].side",  "最近成交方向 BUY/SELL。"),
            ("fetched_at",        "DateTime",                "(本地)",          "抓取时间。"),
        ],
    },

    "clob_orderbook": {
        "title": "polymetl.clob_orderbook  —  订单簿快照（所有买卖档位）",
        "intro":
            "对每个 accepting_orders=true 的 token 调用 GET /book?token_id=…。"
            "API 返回买盘 (bids) 与卖盘 (asks) 数组，每元素 {price, size}；"
            "我们拍平为一行 = (token, side, price, size)。"
            "MergeTree (非 Replacing) 按天分区——每次抓取 append 新快照，便于做时间序列分析。"
            "查询「最新」需 WHERE fetched_at = (SELECT max…)，或按需用 final fetched_at 过滤。",
        "endpoint": "GET /book?token_id=…",
        "engine":   "MergeTree PARTITION BY toYYYYMMDD(fetched_at) ORDER BY (token_id, side, price, fetched_at)",
        "cols": [
            ("token_id",        "String",                 "asset_id / token_id", "outcome token ID。"),
            ("market",          "String",                 "market",              "对应 conditionId。"),
            ("side",            "LowCardinality(String)", "(派生)",               "'bid' / 'ask'。"),
            ("price",           "Float64",                "bids[*].price / asks[*].price", "档位价格（USDC/share）。"),
            ("size",            "Float64",                "bids[*].size / asks[*].size",   "档位深度（shares）。"),
            ("book_timestamp",  "UInt64",                 "timestamp",           "API 返回的 server-side 时间戳（毫秒）。"),
            ("book_hash",       "String",                 "hash",                "订单簿哈希；同一 token 两次抓取若 hash 相同则书未变。"),
            ("fetched_at",      "DateTime",               "(本地)",               "抓取时间。"),
        ],
    },

    "clob_prices_history": {
        "title": "polymetl.clob_prices_history  —  历史价格时序（小时粒度）",
        "intro":
            "对每个 outcome token（含已关闭市场，~2.06M 个）调用 "
            "GET /prices-history?market=…&startTs=…&endTs=…&fidelity=60，"
            "返回 {history: [{t, p}, ...]}。t 是 unix 秒，p 是 USDC/share ∈ [0, 1]。"
            "API 静默忽略 startTs/endTs 之外的过滤参数，"
            "fidelity 单位为分钟、最小 10。本表用 60（小时线），"
            "兼顾分辨率与体积（每 token 上线 6 个月约 4,000 点）。"
            "如要分钟线，重跑时改 fidelity_min=10。",
        "endpoint": "GET /prices-history?market=<token_id>&fidelity=60&startTs=…&endTs=…",
        "engine":   "ReplacingMergeTree(fetched_at) PARTITION BY toYYYYMM(t) ORDER BY (token_id, t)",
        "cols": [
            ("token_id",     "String",   "(filter)",  "outcome token ID。"),
            ("t",            "DateTime", "history[*].t",  "采样点 UTC 时间（由 unix 秒转换）。"),
            ("p",            "Float64",  "history[*].p",  "采样点价格（USDC/share，∈[0,1]）。"),
            ("fidelity_min", "UInt32",   "(参数)",      "采样粒度（分钟）；本批次为 60。"),
            ("fetched_at",   "DateTime", "(本地)",      "抓取时间。"),
        ],
    },

    "clob_progress": {
        "title": "polymetl.clob_progress  —  抓取进度记录（断点续跑）",
        "intro":
            "每成功处理一个 (endpoint, key) 写入一行（key = token_id 或 condition_id）。"
            "row_count=0 表示 API 返回空（合法情形：closed token 无 orderbook）。"
            "再次启动爬虫时跳过已记录的 key；要强制重抓就 DELETE 对应行。",
        "endpoint": "(internal bookkeeping; not from API)",
        "engine":   "ReplacingMergeTree(updated_at) ORDER BY (endpoint, key)",
        "cols": [
            ("endpoint",   "LowCardinality(String)", "(local)", "枚举：'markets' / 'quotes' / 'orderbook' / 'prices_history'。"),
            ("key",        "String",   "(local)",                "已处理的 token_id 或 condition_id。"),
            ("row_count",  "UInt32",   "(local)",                "本次写入的 API 行数。"),
            ("updated_at", "DateTime", "(local)",                "完成时间。"),
        ],
    },
}


def fmt_pct(v: float) -> str:
    return f"{v:.1%}"


def compute_table_stats(client: Client, table: str, cols: list[tuple[str, str, str, str]]):
    total = client.execute(f"SELECT count() FROM polymetl.{table} FINAL")[0][0]
    if total == 0:
        return 0, {c[0]: 0.0 for c in cols}
    parts = []
    for name, ctype, _src, _desc in cols:
        if ctype.startswith("String") or ctype.startswith("LowCardinality(String)"):
            cond = f"{name} != ''"
        elif ctype.startswith("Nullable(DateTime)"):
            cond = f"{name} IS NOT NULL"
        elif ctype == "DateTime":
            cond = f"toUnixTimestamp({name}) > 0"
        elif ctype.startswith("Array"):
            cond = f"length({name}) > 0"
        else:
            cond = f"{name} != 0"
        parts.append(f"countIf({cond}) AS f_{name}")
    sql = f"SELECT {', '.join(parts)} FROM polymetl.{table} FINAL"
    row = client.execute(sql)[0]
    return total, {cols[i][0]: row[i] / total for i in range(len(cols))}


def styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=CJK,
                             fontSize=18, leading=23, spaceAfter=6,
                             textColor=colors.HexColor("#0f172a")),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=CJK,
                             fontSize=13, leading=17, spaceBefore=14, spaceAfter=4,
                             textColor=colors.HexColor("#0f172a")),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=CJK,
                               fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=4),
        "caption": ParagraphStyle("caption", parent=base["BodyText"], fontName=CJK,
                                  fontSize=8, leading=11, textColor=colors.grey,
                                  spaceAfter=8),
        "code": ParagraphStyle("code", parent=base["BodyText"], fontName=MONO,
                               fontSize=8, leading=11, leftIndent=8,
                               backColor=colors.HexColor("#f1f5f9"),
                               borderPadding=4, spaceAfter=8),
        "celldesc": ParagraphStyle("cd", fontName=CJK, fontSize=8, leading=11,
                                   textColor=colors.HexColor("#1e293b")),
    }


def build_table(cols, fills, s):
    data = [["列名", "类型", "API 源字段", "覆盖率", "中文说明"]]
    for name, ctype, src, desc in cols:
        data.append([
            Paragraph(f"<font name='{MONO}' size='8'>{name}</font>", s["celldesc"]),
            Paragraph(f"<font name='{MONO}' size='8'>{ctype}</font>", s["celldesc"]),
            Paragraph(f"<font name='{MONO}' size='8'>{src}</font>", s["celldesc"]),
            fmt_pct(fills.get(name, 0.0)),
            Paragraph(desc, s["celldesc"]),
        ])
    t = Table(data, colWidths=[3.7*cm, 3.0*cm, 2.7*cm, 1.5*cm, 7.1*cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (-1, 0), CJK),
        ("FONTSIZE",  (0, 0), (-1, 0), 9),
        ("BACKGROUND",(0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN",     (3, 1), (3, -1), "RIGHT"),
        ("VALIGN",    (0, 0), (-1, -1),"TOP"),
        ("GRID",      (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
            [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ]))
    return t


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(Path.home() / "Desktop" / "polymetl_clob_dictionary.pdf"),
    )
    parser.add_argument("--host",     default=os.getenv("POLYMETL_CLICKHOUSE_HOST", "localhost"))
    parser.add_argument("--port",     type=int, default=int(os.getenv("POLYMETL_CLICKHOUSE_PORT", "9000")))
    parser.add_argument("--user",     default=os.getenv("POLYMETL_CLICKHOUSE_USER", "default"))
    parser.add_argument("--password", default=os.getenv("POLYMETL_CLICKHOUSE_PASSWORD", ""))
    parser.add_argument("--database", default=os.getenv("POLYMETL_CLICKHOUSE_DATABASE", "polymetl"))
    args = parser.parse_args()

    pdfmetrics.registerFont(UnicodeCIDFont(CJK))
    s = styles()

    client = Client(host=args.host, port=args.port, user=args.user,
                    password=args.password, database=args.database)

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.6*cm,  bottomMargin=1.6*cm,
        title="polymetl CLOB 数据字典",
        author="PolyMetl",
    )

    story = []
    story.append(Paragraph("polymetl CLOB 数据字典", s["h1"]))
    story.append(Paragraph(
        "数据源：https://clob.polymarket.com（公开 REST，无需鉴权）。"
        "本字典覆盖 5 张 ClickHouse 表 + 4 个可爬端点。"
        "覆盖率 = 该列「有意义值」的占比（String 非空、数值非 0、DateTime 非 0、Array 非空）；"
        "0% 多半意味着该表正在抓取中，待 prices_history 跑完后重新生成 PDF 即可。",
        s["caption"],
    ))

    story.append(Paragraph("API 限制与抓取策略", s["h2"]))
    story.append(Paragraph(
        "<b>(1)</b> /markets 用 cursor 分页（next_cursor base64 字符串），limit 上限 1,000，无 offset 限制；"
        "<b>(2)</b> /book、/midpoint、/spread 仅对 accepting_orders=true 的 token 返回；"
        "<b>(3)</b> /prices-history 的 fidelity 单位为分钟、最小 10，时间过滤静默忽略，"
        "需显式给 startTs/endTs 才能拉到历史数据；"
        "<b>(4)</b> POST 批量端点（/midpoints、/spreads、/prices、/last-trades-prices、/books）"
        "支持单次 100+ token，强烈建议批量取，避免每 token 一次 GET。"
        "<b>(5)</b> CLOB 暴露的市场数（约 1.07M）远多于 Gamma 的 146k——"
        "前者包含 NegRisk 子市场、归档/测试市场、AMM 时代未上 Gamma UI 的旧市场。",
        s["body"],
    ))

    for tbl_key, meta in TABLE_DEFS.items():
        cols = meta["cols"]
        try:
            total, fills = compute_table_stats(client, tbl_key, cols)
        except Exception:
            total, fills = 0, {c[0]: 0.0 for c in cols}

        story.append(Paragraph(meta["title"], s["h2"]))
        story.append(Paragraph(
            f"<b>当前行数</b>：{total:,}  "
            f"&nbsp;&nbsp;<b>API 端点</b>：<font name='{MONO}'>{meta['endpoint']}</font>  "
            f"&nbsp;&nbsp;<b>表引擎</b>：<font name='{MONO}'>{meta['engine']}</font>",
            s["body"],
        ))
        story.append(Paragraph(meta["intro"], s["body"]))
        story.append(build_table(cols, fills, s))
        story.append(Spacer(1, 0.2*cm))

    story.append(PageBreak())
    story.append(Paragraph("常用查询样例", s["h2"]))

    story.append(Paragraph("1. 把 CLOB 价格时序与 markets_full 合并，取「2024 大选 Trump YES」全周期日线：", s["body"]))
    story.append(Paragraph(
        "WITH trump_yes AS (<br/>"
        "  SELECT JSONExtractString(token, 'token_id') AS tid<br/>"
        "  FROM polymetl.clob_markets FINAL<br/>"
        "  ARRAY JOIN JSONExtractArrayRaw(tokens_json) AS token<br/>"
        "  WHERE market_slug='will-donald-trump-win-the-2024-us-presidential-election'<br/>"
        "    AND JSONExtractString(token, 'outcome')='Yes'<br/>"
        ")<br/>"
        "SELECT t, p<br/>"
        "FROM polymetl.clob_prices_history<br/>"
        "WHERE token_id IN (SELECT tid FROM trump_yes)<br/>"
        "ORDER BY t;",
        s["code"],
    ))

    story.append(Paragraph("2. 当前订单簿 top-of-book（合并 quotes + orderbook，便于核对）：", s["body"]))
    story.append(Paragraph(
        "SELECT q.token_id, q.midpoint, q.best_bid, q.best_ask,<br/>"
        "       o.price AS top_bid_price, o.size AS top_bid_size<br/>"
        "FROM polymetl.clob_quotes FINAL q<br/>"
        "LEFT JOIN (<br/>"
        "  SELECT token_id, argMax(price, fetched_at) AS price,<br/>"
        "         argMax(size, fetched_at) AS size<br/>"
        "  FROM polymetl.clob_orderbook<br/>"
        "  WHERE side='bid'<br/>"
        "  GROUP BY token_id<br/>"
        ") o USING token_id<br/>"
        "LIMIT 20;",
        s["code"],
    ))

    story.append(Paragraph("3. 价格波动率（小时收益率标准差），按市场聚合：", s["body"]))
    story.append(Paragraph(
        "WITH ret AS (<br/>"
        "  SELECT token_id, t, p, lagInFrame(p) OVER (PARTITION BY token_id ORDER BY t) AS p_prev<br/>"
        "  FROM polymetl.clob_prices_history<br/>"
        ")<br/>"
        "SELECT token_id, stddevPop(log(p / p_prev)) AS hourly_log_vol<br/>"
        "FROM ret<br/>"
        "WHERE p_prev &gt; 0 AND p &gt; 0<br/>"
        "GROUP BY token_id ORDER BY hourly_log_vol DESC LIMIT 20;",
        s["code"],
    ))

    story.append(Paragraph("4. 按 NegRisk 父 market 聚合所有子市场的当前 OI（结合 dataapi_oi）：", s["body"]))
    story.append(Paragraph(
        "SELECT m.neg_risk_market_id, sum(oi.value) AS total_oi<br/>"
        "FROM polymetl.clob_markets FINAL m<br/>"
        "JOIN polymetl.dataapi_oi FINAL oi<br/>"
        "  ON oi.market = m.condition_id<br/>"
        "WHERE m.neg_risk = 1<br/>"
        "GROUP BY m.neg_risk_market_id ORDER BY total_oi DESC LIMIT 10;",
        s["code"],
    ))

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        "© 2026 PolyMetl 毕业论文项目。爬虫源码：polymetl/src/clob_api.py。"
        "覆盖率统计现取自实表，会随后续抓取更新。",
        s["caption"],
    ))

    doc.build(story)
    size_kb = out_path.stat().st_size / 1024
    print(f"wrote {out_path}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
