"""
Generate ~/Desktop/polymetl_dataapi_dictionary.pdf — data dictionary for the
four data-api ClickHouse tables:

  - polymetl.dataapi_oi          (open interest snapshot per market)
  - polymetl.dataapi_holders     (current top holders per outcome token)
  - polymetl.dataapi_trades      (historical trades per market, capped at 3000)
  - polymetl.dataapi_progress    (per-endpoint, per-market crawl bookkeeping)

Each column row shows: column name, ClickHouse type, source data-api JSON
field, computed fill-rate (% non-empty), and a Chinese description.

Usage:
    uv run python scripts/build_dataapi_dictionary_pdf.py
    uv run python scripts/build_dataapi_dictionary_pdf.py --out ~/Desktop/foo.pdf
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


# ---------------------------------------------------------------------------
# Per-table column metadata
#   (col_name, ch_type, source_api_field, description_chinese)
# ---------------------------------------------------------------------------
TABLE_DEFS: dict[str, dict] = {
    "dataapi_oi": {
        "title": "polymetl.dataapi_oi  —  当前未平仓量（Open Interest）快照",
        "intro":
            "对每个 market（conditionId）请求 /oi?market=<condId>，返回当前 USDC 计价的"
            "未平仓总额（即所有未结算的 outcome token 头寸的市场价值之和）。"
            "也包含 market='GLOBAL' 单行作为全平台 OI。"
            "ReplacingMergeTree(fetched_at) ORDER BY market — 重复抓取时自动用最新值覆盖。",
        "endpoint": "GET /oi?market=<conditionId>",
        "engine":   "ReplacingMergeTree(fetched_at) ORDER BY market",
        "cols": [
            ("market",        "String",   "market",       "市场 conditionId（66 字符，含 0x）；特殊值 'GLOBAL' 表示全平台 OI 汇总。"),
            ("value",         "Float64",  "value",        "未平仓量（USDC，最小单位浮点数）。"),
            ("fetched_at",    "DateTime", "(bookkeeping)","本行写入时间，同时是 ReplacingMergeTree 的 version 列。"),
        ],
    },

    "dataapi_holders": {
        "title": "polymetl.dataapi_holders  —  当前 outcome token 持有者快照",
        "intro":
            "对每个 market 请求 /holders?market=<condId>&limit=1000。"
            "API 按 outcome 拆分返回（典型二元市场返回 2 段），每段最多 1000 个持有者。"
            "我们把嵌套结构拍平：一行对应一个 (market, outcome token, wallet) 三元组。"
            "ReplacingMergeTree(fetched_at) ORDER BY (condition_id, asset, proxy_wallet) — "
            "重新抓取同一 (market, asset, wallet) 时按 fetched_at 保留最新行。"
            "注意：API 限流意味着这是「Top 1000 by amount」，不是全量 holders。",
        "endpoint": "GET /holders?market=<conditionId>&limit=1000",
        "engine":   "ReplacingMergeTree(fetched_at) ORDER BY (condition_id, asset, proxy_wallet)",
        "cols": [
            ("condition_id",   "String",  "(filter)",      "我们请求时传入的 conditionId；与 markets_full.condition_id 可 JOIN。"),
            ("asset",          "String",  "asset / token", "ERC1155 outcome token ID（uint256 字符串）；同一 condition_id 下不同 asset 对应不同结果。"),
            ("outcome_index",  "UInt8",   "outcomeIndex",  "outcome 索引（0/1/...）；与 markets_full.outcomes 数组按位置对齐。"),
            ("proxy_wallet",   "String",  "proxyWallet",   "持有人 Polymarket 代理钱包地址（小写，统一格式便于 JOIN）；与 trades.proxy_wallet 可 JOIN。"),
            ("amount",         "Float64", "amount",        "当前持有的 outcome token 数量（shares）。注意单位是 share，不是美元；USDC 价值 = amount × outcome_prices[outcome_index]。"),
            ("display_name",   "String",  "name",          "用户在 Polymarket 上的可显示名（用户自定义；可能是地址首尾、Twitter handle 或自定义 nickname）。"),
            ("pseudonym",      "String",  "pseudonym",     "Polymarket 自动分配的伪名（如 Shocked-Acetate、Slow-Minute），即便用户未设名也可用作标识。"),
            ("bio",            "String",  "bio",           "用户填写的个人简介（多数为空）。"),
            ("profile_image",  "String",  "profileImage",  "用户头像 URL。"),
            ("profile_image_optimized", "String", "profileImageOptimized", "针对 UI 缩放的头像 URL（thumbnail）。"),
            ("verified",       "UInt8",   "verified",      "1 = 该钱包通过 Polymarket 身份验证（极少）。"),
            ("display_username_public", "UInt8", "displayUsernamePublic", "1 = 公开显示用户名；0 = 仅显示 pseudonym。"),
            ("fetched_at",     "DateTime","(bookkeeping)", "抓取时间。"),
        ],
    },

    "dataapi_trades": {
        "title": "polymetl.dataapi_trades  —  历史成交流水",
        "intro":
            "对每个 market 请求 /trades?market=<condId>&limit=1000，offset 0/1000/2000 分三页拉取，"
            "API 返回最近 3,000 笔成交（再老的拿不到）。"
            "高交易量市场（如 Trump 2024）会被截断到 3,000 笔；低交易量市场则全量入库。"
            "每行对应一笔 fill；同一 (tx_hash, asset, proxy_wallet) 唯一。"
            "ReplacingMergeTree(fetched_at) PARTITION BY toYYYYMM(trade_time) — "
            "按月分区便于按时间窗口查询。",
        "endpoint": "GET /trades?market=<conditionId>&limit=1000&offset=N (N ∈ {0,1000,2000})",
        "engine":   "ReplacingMergeTree(fetched_at) PARTITION BY toYYYYMM(trade_time) ORDER BY (condition_id, trade_time, tx_hash, asset, proxy_wallet)",
        "cols": [
            ("condition_id",   "String",   "conditionId",    "市场 conditionId；与 markets_full.condition_id JOIN 拿题目元数据。"),
            ("tx_hash",        "String",   "transactionHash","Polygon 交易哈希；同一 tx 内可能有多笔 fill，配合 asset/proxy_wallet 区分。"),
            ("trade_time",     "DateTime", "timestamp",      "成交 UTC 时间（由 unix timestamp 转换）；用作主排序键之一。"),
            ("proxy_wallet",   "String",   "proxyWallet",    "成交方钱包（taker 视角，已小写）；与 holders.proxy_wallet 可 JOIN。"),
            ("side",           "String",   "side",           "BUY / SELL（taker 视角对该 outcome token 的方向）。"),
            ("asset",          "String",   "asset",          "成交 outcome token ID（uint256 字符串）；选定了二元市场的某一边。"),
            ("size",           "Float64",  "size",           "成交数量（outcome token shares）。"),
            ("price",           "Float64", "price",          "成交价（USDC/share，∈ [0, 1]）。"),
            ("outcome",         "String",  "outcome",        "成交的 outcome 标签字符串（如 Yes/No/Up/Down/Trump）。"),
            ("outcome_index",   "UInt8",   "outcomeIndex",   "outcome 数组索引（与 outcomes 字段对齐）。"),
            ("title",           "String",  "title",          "市场题目快照（冗余便于直查），与 markets_full.question 等价。"),
            ("slug",            "String",  "slug",           "市场 slug 快照。"),
            ("event_slug",      "String",  "eventSlug",      "父 event 的 slug（多市场 NegRisk 组共用一个 event）。"),
            ("icon",            "String",  "icon",           "市场图标 URL。"),
            ("display_name",    "String",  "name",           "成交者用户名。"),
            ("pseudonym",       "String",  "pseudonym",      "Polymarket 伪名。"),
            ("bio",             "String",  "bio",            "成交者简介（多为空）。"),
            ("profile_image",   "String",  "profileImage",   "头像 URL。"),
            ("profile_image_optimized", "String", "profileImageOptimized", "缩略图头像 URL。"),
            ("fetched_at",      "DateTime","(bookkeeping)",  "抓取时间。"),
        ],
    },

    "dataapi_progress": {
        "title": "polymetl.dataapi_progress  —  抓取进度记录（断点续跑）",
        "intro":
            "每成功处理一个 (endpoint, condition_id) 组合，写入一行；下一次跑爬虫时跳过已处理项。"
            "若 row_count=0，说明该端点对该市场返回为空（合法情形：低交易量市场无 trades 等）。"
            "若想强制重抓某市场，从该表删掉对应行即可。",
        "endpoint": "(internal bookkeeping; not from API)",
        "engine":   "ReplacingMergeTree(updated_at) ORDER BY (endpoint, condition_id)",
        "cols": [
            ("endpoint",     "String",   "(local)",      "枚举值：'oi' / 'holders' / 'trades'。"),
            ("condition_id", "String",   "(local)",      "已处理的 conditionId。"),
            ("row_count",    "UInt32",   "(local)",      "本次写入的 API 行数；为 0 表示该端点对该市场返回为空。"),
            ("updated_at",   "DateTime", "(local)",      "完成时间。"),
        ],
    },
}


# ---------------------------------------------------------------------------
# Live coverage stats
# ---------------------------------------------------------------------------
def fmt_pct(v: float) -> str:
    return f"{v:.1%}"


def compute_table_stats(client: Client, table: str, cols: list[tuple[str, str, str, str]]):
    """Return (total_rows, {col_name: fill_rate})."""
    total = client.execute(f"SELECT count() FROM polymetl.{table} FINAL")[0][0]
    if total == 0:
        return 0, {c[0]: 0.0 for c in cols}
    parts = []
    for name, ctype, _src, _desc in cols:
        if ctype.startswith("String"):
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


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------
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
    t = Table(data, colWidths=[3.7*cm, 2.6*cm, 2.7*cm, 1.6*cm, 7.4*cm], repeatRows=1)
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
        default=str(Path.home() / "Desktop" / "polymetl_dataapi_dictionary.pdf"),
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
        title="polymetl data-api 数据字典",
        author="PolyMetl",
    )

    story = []
    story.append(Paragraph("polymetl data-api 数据字典", s["h1"]))
    story.append(Paragraph(
        "数据源：https://data-api.polymarket.com（公开 REST 接口，无需鉴权）。"
        "本字典覆盖四张 ClickHouse 表，对应三个可爬端点（/oi、/holders、/trades）"
        "外加进度元表。覆盖率定义：String 非空、数值非 0、DateTime 非 0 时戳。"
        "覆盖率为 0 时该表可能尚未抓取完毕——请重新生成 PDF。",
        s["caption"],
    ))

    story.append(Paragraph("API 限制与抓取策略", s["h2"]))
    story.append(Paragraph(
        "data-api 的关键约束："
        "<b>(1)</b> /trades 的 offset 上限为 3000，limit 上限 1000，故每个市场最多取最近 3,000 笔成交；"
        "<b>(2)</b> 时间过滤参数（fromTimestamp、before、after 等）均被服务端静默忽略；"
        "<b>(3)</b> /holders 不分页，仅返回每个 outcome token 的 Top-1000 持有者；"
        "<b>(4)</b> User-Agent 必须模拟浏览器，否则被 WAF 拦截 403。"
        "因此「全量爬取」实际是按 markets_full 中的 146,190 个 conditionId 逐一发请求，"
        "对每个市场最多得 3,000 笔成交 + 2,000 个 holders + 1 行 OI。",
        s["body"],
    ))

    for tbl_key, meta in TABLE_DEFS.items():
        cols = meta["cols"]
        try:
            total, fills = compute_table_stats(client, tbl_key, cols)
        except Exception as e:
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

    # ---------- Helpful joins / queries ----------
    story.append(PageBreak())
    story.append(Paragraph("常用 JOIN / 查询样例", s["h2"]))
    story.append(Paragraph(
        "1. 把 trades 与 markets_full 元数据连起来：",
        s["body"],
    ))
    story.append(Paragraph(
        "SELECT t.trade_time, t.proxy_wallet, t.size, t.price, m.question<br/>"
        "FROM polymetl.dataapi_trades t<br/>"
        "JOIN polymetl.markets_full FINAL m ON t.condition_id = m.condition_id<br/>"
        "WHERE m.fpmm_live = 0 AND m.volume &gt; 1e6<br/>"
        "ORDER BY t.trade_time DESC LIMIT 100;",
        s["code"],
    ))
    story.append(Paragraph(
        "2. 单一市场的持仓集中度（前 10% 钱包占比）：",
        s["body"],
    ))
    story.append(Paragraph(
        "SELECT condition_id,<br/>"
        "       sum(amount) AS total_shares,<br/>"
        "       quantilesExact(0.9)(amount) AS p90<br/>"
        "FROM polymetl.dataapi_holders<br/>"
        "GROUP BY condition_id LIMIT 5;",
        s["code"],
    ))
    story.append(Paragraph(
        "3. 钱包级别的「在哪些市场交易过」（基于 trades 与 holders 取并集）：",
        s["body"],
    ))
    story.append(Paragraph(
        "SELECT proxy_wallet, count(DISTINCT condition_id) AS n_markets<br/>"
        "FROM polymetl.dataapi_trades<br/>"
        "GROUP BY proxy_wallet ORDER BY n_markets DESC LIMIT 20;",
        s["code"],
    ))
    story.append(Paragraph(
        "4. 全平台 OI 时间序列（每次抓取追加一行 'GLOBAL'）：",
        s["body"],
    ))
    story.append(Paragraph(
        "SELECT fetched_at, value FROM polymetl.dataapi_oi<br/>"
        "WHERE market='GLOBAL' ORDER BY fetched_at;",
        s["code"],
    ))

    # ---------- Footer ----------
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        "© 2026 PolyMetl 毕业论文项目。爬虫源码：polymetl/src/data_api.py。"
        "覆盖率统计现取自实表，会随后续抓取更新。",
        s["caption"],
    ))

    doc.build(story)
    size_kb = out_path.stat().st_size / 1024
    print(f"wrote {out_path}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
