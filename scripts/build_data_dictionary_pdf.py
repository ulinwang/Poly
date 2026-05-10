"""
Generate ~/Desktop/polymetl_markets_full_dictionary.pdf — a per-column
data dictionary for the 128-column polymetl.markets_full table.

For each column we emit:
  - column name (snake_case, as in ClickHouse)
  - ClickHouse data type
  - source key (the original Gamma API JSON field)
  - Chinese description
  - fill rate (% of rows where the column is non-empty / non-null / non-zero,
               computed live from polymetl.markets_full FINAL)

Usage:
    uv run python scripts/build_data_dictionary_pdf.py
    uv run python scripts/build_data_dictionary_pdf.py --out ~/Desktop/foo.pdf
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

from src.gamma_full import FIELDS, EXTRA_COLS


CJK = "STSong-Light"
MONO = "Courier"


# ---------- Per-section ordering ----------
# Mirrors the FIELDS layout in src/gamma_full.py so readers can navigate
# the dictionary by purpose, not alphabetically.
SECTIONS: list[tuple[str, list[str]]] = [
    ("一、标识 / Identifiers", [
        "market_id", "slug", "question", "description", "question_id",
        "condition_id", "market_maker_address", "creator", "submitted_by",
        "category", "subcategory", "category_mailchimp_tag", "mailchimp_tag",
        "market_type", "sports_market_type", "format_type", "denomination_token",
        "game_id", "group_item_title", "group_item_threshold",
    ]),
    ("二、媒体 / Media", [
        "icon", "image", "twitter_card_image", "sponsor_image", "series_color",
    ]),
    ("三、结果与解析 / Outcomes & Resolution", [
        "outcomes", "clob_token_ids", "outcome_prices",
        "uma_resolution_statuses", "uma_resolution_status",
        "resolved_by", "resolution_source", "automatically_resolved",
        "lower_bound", "upper_bound", "line",
    ]),
    ("四、订单簿与定价 / Order Book & Pricing", [
        "last_trade_price", "best_bid", "best_ask", "spread",
        "order_min_size", "order_price_min_tick_size",
        "rewards_min_size", "rewards_max_spread", "competitive",
    ]),
    ("五、交易量(多窗口) / Volume", [
        "volume", "volume_clob", "volume_num",
        "volume_24hr", "volume_1wk", "volume_1mo", "volume_1yr",
        "volume_24hr_clob", "volume_1wk_clob", "volume_1mo_clob", "volume_1yr_clob",
        "volume_1wk_amm", "volume_1mo_amm", "volume_1yr_amm",
    ]),
    ("六、流动性 / Liquidity", [
        "liquidity", "liquidity_clob", "liquidity_amm", "liquidity_num",
    ]),
    ("七、价格变化 / Price Change", [
        "one_hour_price_change", "one_day_price_change",
        "one_week_price_change", "one_month_price_change", "one_year_price_change",
    ]),
    ("八、时间戳 / Timestamps", [
        "start_date", "start_date_iso", "end_date", "end_date_iso",
        "uma_end_date", "closed_time", "created_at", "updated_at",
        "accepting_orders_timestamp", "deploying_timestamp", "game_start_time",
    ]),
    ("九、状态标志 / Status Flags", [
        "active", "closed", "archived", "restricted",
        "enable_order_book", "accepting_orders", "funded", "approved",
        "ready", "deploying", "automatically_active", "pending_deployment",
        "manual_activation", "clear_book_on_start", "cyom", "featured",
        "fees_enabled", "fpmm_live", "has_reviewed_dates",
        "holding_rewards_enabled", "is_new", "notifications_enabled",
        "pager_duty_notification_enabled", "ready_for_cron",
        "requires_translation", "rfq_enabled", "sent_discord",
        "show_gmp_outcome", "show_gmp_series", "wide_format",
        "neg_risk", "neg_risk_other",
    ]),
    ("十、手续费 / Fees", [
        "fee", "fee_type", "maker_base_fee", "taker_base_fee", "fee_schedule_json",
    ]),
    ("十一、UMA 仲裁 / UMA Arbitration", [
        "uma_bond", "uma_reward", "custom_liveness",
        "neg_risk_market_id", "neg_risk_request_id",
    ]),
    ("十二、其他 / Misc", [
        "seconds_delay", "updated_by",
    ]),
    ("十三、嵌套 JSON / Nested JSON", [
        "events_json", "clob_rewards_json", "tags_json",
    ]),
    ("十四、记录元信息 / Bookkeeping", [
        "raw_json", "fetched_at",
    ]),
]


# ---------- Per-column Chinese descriptions ----------
# Goal: 1 sentence each, focused on semantics, not type (type is shown separately).
DESCRIPTIONS: dict[str, str] = {
    # Identifiers
    "market_id":               "Polymarket 内部市场唯一 ID（Gamma API 字段名为 id）。所有分析的主键。",
    "slug":                    "URL 友好的市场标识，例如 will-donald-trump-win-the-2024-us-presidential-election。",
    "question":                "市场的主问题文本，对用户呈现的字面问题。",
    "description":             "详细的解析规则与背景说明，可达 2000 字符以上，包含数据来源、判定标准、特殊情况处理。",
    "question_id":             "UMA 仲裁系统使用的问题 ID（与 Polymarket market_id 不同）。",
    "condition_id":            "链上 ConditionalToken 合约（CTF）的 conditionId（bytes32）；与 clob_token_ids 一起定位链上头寸；查询链上 payoutNumerators 时的关键字段。",
    "market_maker_address":    "Polymarket 交易合约地址（多市场共用同一交易合约，因此通常同值）。",
    "creator":                 "市场创建者钱包地址，仅 cyom（用户自创建）市场非空。",
    "submitted_by":            "提交者标识（人名或钱包），用于 cyom 市场。",
    "category":                "顶层分类标签（Politics、Sports、Crypto…），覆盖率较低；真实分类常嵌入 events_json。",
    "subcategory":             "子分类，目前几乎不填。",
    "category_mailchimp_tag":  "用于 Polymarket 内部邮件营销分组的分类映射，分析无关。",
    "mailchimp_tag":           "Polymarket 邮件营销标签，分析无关。",
    "market_type":             "市场结构类型，常见值 normal / scalar / categorical。",
    "sports_market_type":      "体育子类型，例如 spread、moneyline、total。仅体育市场非空。",
    "format_type":             "市场显示格式，少见，分析中通常忽略。",
    "denomination_token":      "结算代币（默认 USDC）。极少非默认情况。",
    "game_id":                 "外部体育数据提供商（如 Sportradar）的赛事 ID，用于体育类市场对账。",
    "group_item_title":        "在父 event 中的副标题（如 Trump 在大选 event 下的副标题），用于 UI 列表。",
    "group_item_threshold":    "对 scalar 市场，是阈值字符串（如 '4500' 表示 ETH 价格区间）。",

    # Media
    "icon":                    "市场封面 icon URL。",
    "image":                   "市场展示主图 URL。",
    "twitter_card_image":      "Twitter 卡片图 URL。",
    "sponsor_image":           "赞助商展示图 URL（如 sponsored 市场）。",
    "series_color":            "在 series（系列）中显示的主题色（hex 字符串）。",

    # Outcomes & Resolution
    "outcomes":                "结果标签数组，例如 [Yes, No]、[Up, Down]、[Trump, Harris, Biden]。位置与 outcome_prices 一一对应。",
    "clob_token_ids":          "对应每个 outcome 的链上 ERC1155 token ID（uint256 字符串），与 OrderFilled.maker_asset_id / taker_asset_id 可 JOIN。",
    "outcome_prices":          "结算后或当前价格快照（Float64 数组）。已结算时来自 CTF payoutNumerators / payoutDenominator；未结算时来自 CLOB 中价或 AMM implied price。详见 outcome_prices_explained.pdf。",
    "uma_resolution_statuses": "每个 outcome 的 UMA 解析状态数组，常见值 resolved / settled / proposed / disputed。",
    "uma_resolution_status":   "市场层面的 UMA 解析状态（数组的概要）。已结算市场约 92.9% 为 resolved。",
    "resolved_by":             "触发结算的钱包地址（通常是 UMA 仲裁者或自动机器人）。",
    "resolution_source":       "判定依据的资料来源 URL（新闻链接、官方比分页等）。覆盖率约 39%。",
    "automatically_resolved":  "1 = 通过预言机自动结算；0 = 经 UMA 人工提议/争议。",
    "lower_bound":             "scalar 市场的下界（字符串，可能含单位）。仅 13/600 抽样市场非空。",
    "upper_bound":             "scalar 市场的上界。",
    "line":                    "体育让分盘口（如 -3.5 表示让 3.5 分），仅特定盘口类型非空。",

    # Order book & Pricing
    "last_trade_price":        "CLOB 最近一次成交价（YES outcome 视角，∈ [0, 1] USDC/share）。",
    "best_bid":                "当前 CLOB 买方最优报价。市场冷清时可能为 0。",
    "best_ask":                "当前 CLOB 卖方最优报价。",
    "spread":                  "best_ask - best_bid，做市商深度的衡量。",
    "order_min_size":          "下单最小份额（shares）。",
    "order_price_min_tick_size":"价格最小步进（如 0.001 USDC/share）。",
    "rewards_min_size":        "做市奖励要求的最小订单规模。",
    "rewards_max_spread":      "做市奖励允许的最大 spread。",
    "competitive":             "Polymarket 内部计算的「竞争性」分数（混合流动性和价差），分布范围 [0, 1] 区间。",

    # Volume
    "volume":                  "市场全周期累计交易量（USDC）。",
    "volume_clob":             "CLOB 渠道的累计交易量。",
    "volume_num":              "数值版的 volume，用于排序，与 volume 略有差异（前者去除了部分作废交易）。",
    "volume_24hr":             "过去 24 小时累计交易量。",
    "volume_1wk":              "过去 7 天累计交易量。",
    "volume_1mo":              "过去 30 天累计交易量。",
    "volume_1yr":              "过去 365 天累计交易量。",
    "volume_24hr_clob":        "过去 24 小时 CLOB 渠道交易量。",
    "volume_1wk_clob":         "过去 7 天 CLOB 渠道交易量。",
    "volume_1mo_clob":         "过去 30 天 CLOB 渠道交易量。",
    "volume_1yr_clob":         "过去 365 天 CLOB 渠道交易量。",
    "volume_1wk_amm":          "过去 7 天 AMM 渠道交易量（仅 fpmm_live=1 的旧市场非零）。",
    "volume_1mo_amm":          "过去 30 天 AMM 渠道交易量。",
    "volume_1yr_amm":          "过去 365 天 AMM 渠道交易量。",

    # Liquidity
    "liquidity":               "做市商在订单簿+池子中提供的总流动性（USDC 等价）。",
    "liquidity_clob":          "CLOB 订单簿挂单总美元额。",
    "liquidity_amm":           "AMM 池中流动性（仅 fpmm_live=1）。",
    "liquidity_num":           "数值版 liquidity（用于排序）。",

    # Price changes
    "one_hour_price_change":   "过去 1 小时 YES 价格变化（绝对值，单位 USDC/share）。",
    "one_day_price_change":    "过去 24 小时 YES 价格变化。",
    "one_week_price_change":   "过去 7 天 YES 价格变化。",
    "one_month_price_change":  "过去 30 天 YES 价格变化。",
    "one_year_price_change":   "过去 365 天 YES 价格变化。",

    # Timestamps
    "start_date":              "市场预定开始接受下单的时间（UTC）。",
    "start_date_iso":          "ISO 8601 表示的 start_date（与 start_date 数值相同，仅格式不同）。",
    "end_date":                "市场预定结束/解析的时间。可用作分析窗口截断。",
    "end_date_iso":            "ISO 8601 表示的 end_date。",
    "uma_end_date":            "UMA 提交仲裁的截止时间（通常等于或晚于 end_date）。",
    "closed_time":             "市场实际进入 closed 状态的时间（UMA 解析完成后写入）。已结算市场覆盖率 99.96%。",
    "created_at":              "市场记录在 Gamma 中创建的时间。",
    "updated_at":              "Gamma 数据库最近一次更新该记录的时间。",
    "accepting_orders_timestamp": "开始接收订单的时刻（链上 acceptingOrders=true 的事件时间）。",
    "deploying_timestamp":     "市场链上部署完成时刻。",
    "game_start_time":         "对体育类市场，赛事开赛时间。",

    # Status flags
    "active":                  "1 = 市场在 Polymarket 平台可见；0 = 已隐藏。注意 active=1 不代表可下单。",
    "closed":                  "1 = 市场已解析（outcome_prices 已固定）；0 = 仍在交易/等待解析。",
    "archived":                "1 = 已归档（不再列出在主页面）。",
    "restricted":              "1 = 因合规原因对部分用户限制访问。",
    "enable_order_book":       "1 = 启用 CLOB 订单簿（现代主流）；0 = 仅 AMM 或未启用。",
    "accepting_orders":        "1 = 当前可下单；0 = 暂停下单。",
    "funded":                  "1 = 流动性已注资。",
    "approved":                "1 = Polymarket 团队已批准上线（区分自动生成草稿）。",
    "ready":                   "1 = 准备好接受流量。",
    "deploying":               "1 = 当前正在链上部署。",
    "automatically_active":    "1 = 系统自动激活；0 = 需手动激活。",
    "pending_deployment":      "1 = 部署队列中尚未上链。",
    "manual_activation":       "1 = 手动控制激活。",
    "clear_book_on_start":     "1 = 开盘清空订单簿。",
    "cyom":                    "Create Your Own Market：1 = 用户创建（非官方）。",
    "featured":                "1 = 在首页特色推荐位展示。",
    "fees_enabled":            "1 = 启用手续费收取。",
    "fpmm_live":               "1 = 使用旧的 FPMM (Fixed Product Market Maker) AMM 模型；0 = 现代 CLOB。是「outcome_prices ≈ 0.999...」与多种异常的关键过滤字段。",
    "has_reviewed_dates":      "1 = Polymarket 团队已人工审核过 start/end 日期。",
    "holding_rewards_enabled": "1 = 启用持仓奖励（按持有时间分发）。",
    "is_new":                  "源字段名 new；1 = 在 Polymarket 内部标为新市场（用于 UI 高亮）。",
    "notifications_enabled":   "1 = 启用市场动态推送通知。",
    "pager_duty_notification_enabled": "1 = 异常时通过 PagerDuty 通知 Polymarket 团队（运维内部）。",
    "ready_for_cron":          "1 = 可被定时任务（cron）轮询更新状态。",
    "requires_translation":    "1 = 题目/描述需要翻译为其他语言。",
    "rfq_enabled":             "1 = 启用 RFQ（询价）模式，大单走对手询价而非订单簿。",
    "sent_discord":            "1 = 已通过 Polymarket Discord 频道公告（运营内部）。",
    "show_gmp_outcome":        "GMP（Game Markets Platform）相关 UI 显示标志。",
    "show_gmp_series":         "GMP 系列展示开关。",
    "wide_format":             "1 = 在 UI 中使用宽版排版（如多结果市场）。",
    "neg_risk":                "1 = 此市场属于 NegRisk 拼接组（如「2024 年总统大选」由多个互斥 YES/NO 组合而成）。NegRisk 是 Polymarket 多结果聚合的官方协议。",
    "neg_risk_other":          "在 NegRisk 组中是否为「其他」兜底选项。",

    # Fees
    "fee":                     "手续费率（字符串，常见 0 或基点表示）。",
    "fee_type":                "手续费类型（如 percentage、fixed），覆盖率约 33%。",
    "maker_base_fee":          "做市方基础费率（基点，bps）。",
    "taker_base_fee":          "吃单方基础费率（bps）。",
    "fee_schedule_json":       "手续费阶梯表（JSON 字符串，按持仓量/资格分级）。",

    # UMA arbitration
    "uma_bond":                "UMA 提案/争议时需质押的 UMA 代币数量（字符串，wei 单位）。",
    "uma_reward":              "UMA 提案者获得的奖励（wei）。",
    "custom_liveness":         "自定义 UMA 仲裁等待期（秒）。",
    "neg_risk_market_id":      "在 NegRisk 组中的 market ID（与 condition_id 不同）。",
    "neg_risk_request_id":     "NegRisk 解析请求 ID。",

    # Misc
    "seconds_delay":           "数据延迟（秒），用于实时数据展示。",
    "updated_by":              "最近一次更新该记录的用户/服务 ID。",

    # Nested JSON
    "events_json":             "父级 events 数组（JSON 字符串）：包含 ticker、slug、tags、市场分组等。真实分类信息在这里——查询时用 JSONExtract 解析。",
    "clob_rewards_json":       "CLOB 做市奖励配置（JSON 字符串）：奖励池规模、分发规则、最低订单要求。仅启用奖励的市场非空。",
    "tags_json":               "市场标签数组（JSON 字符串）。本次抓取此字段为空，源 API 当前未在 /markets 端点返回 tags。",

    # Bookkeeping
    "raw_json":                "完整原始 API 响应（JSON 字符串）。当未来需要新字段时，无需重抓 Gamma，直接用 JSONExtract 从此列恢复。",
    "fetched_at":              "本行被 Gamma puller 抓取写入的 UTC 时间。同时是 ReplacingMergeTree 的 version 列——再次抓取时按此列保留最新。",
}


def fmt_pct(v: float) -> str:
    return f"{v:.1%}"


def compute_fill_rates(client: Client) -> tuple[int, dict[str, float]]:
    """For each column, compute the share of rows where it's 'meaningful'.

    Definition by ClickHouse type:
      - String:                       col != ''
      - Nullable(DateTime):           col IS NOT NULL
      - Array(...):                   length(col) > 0
      - Numeric (UInt8/UInt32/Int64/Float64): col != 0   (best proxy for non-default)
      - DateTime:                     col != toDateTime(0)  (always true except sentinel)
    """
    total = client.execute("SELECT count() FROM markets_full FINAL")[0][0]
    if total == 0:
        return 0, {}

    fields_all = list(FIELDS) + [(name, None, ctype, None) for name, ctype in EXTRA_COLS]
    parts = []
    for name, _src, ctype, _kind in fields_all:
        if ctype.startswith("String"):
            cond = f"{name} != ''"
        elif ctype.startswith("Nullable(DateTime)"):
            cond = f"{name} IS NOT NULL"
        elif ctype.startswith("Array"):
            cond = f"length({name}) > 0"
        elif ctype == "DateTime":
            cond = f"toUnixTimestamp({name}) > 0"
        else:
            cond = f"{name} != 0"
        parts.append(f"countIf({cond}) AS f_{name}")

    sql = "SELECT " + ", ".join(parts) + " FROM markets_full FINAL"
    row = client.execute(sql)[0]
    out = {}
    for (name, _src, _ctype, _kind), val in zip(fields_all, row):
        out[name] = val / total
    return total, out


def styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=CJK,
                             fontSize=18, leading=24, spaceAfter=8,
                             textColor=colors.HexColor("#0f172a")),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=CJK,
                             fontSize=12, leading=16, spaceBefore=12, spaceAfter=4,
                             textColor=colors.HexColor("#1e293b")),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=CJK,
                               fontSize=9, leading=12, alignment=TA_LEFT, spaceAfter=4),
        "caption": ParagraphStyle("caption", parent=base["BodyText"], fontName=CJK,
                                  fontSize=8, leading=11, textColor=colors.grey,
                                  spaceAfter=8),
        "code": ParagraphStyle("code", parent=base["BodyText"], fontName=MONO,
                               fontSize=8, leading=11, leftIndent=10,
                               backColor=colors.HexColor("#f1f5f9"),
                               borderPadding=4, spaceAfter=8),
    }


def build_section_table(rows):
    data = [["列名 / Column", "类型 / Type", "Gamma 源字段", "覆盖率", "中文说明"]]
    for r in rows:
        # Wrap long descriptions in Paragraph so cells flow to multi-line
        data.append([
            Paragraph(f"<font name='{MONO}' size='8'>{r['col']}</font>", desc_style),
            Paragraph(f"<font name='{MONO}' size='8'>{r['type']}</font>", desc_style),
            Paragraph(f"<font name='{MONO}' size='8'>{r['src']}</font>", desc_style),
            r["fill"],
            Paragraph(r["desc"], desc_style),
        ])
    t = Table(data, colWidths=[3.6*cm, 2.7*cm, 2.7*cm, 1.6*cm, 6.4*cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME",     (0, 0), (-1, 0),  CJK),
        ("FONTSIZE",     (0, 0), (-1, 0),  9),
        ("BACKGROUND",   (0, 0), (-1, 0),  colors.HexColor("#0f172a")),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("ALIGN",        (3, 1), (3, -1),  "RIGHT"),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("GRID",         (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
            [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ]))
    return t


# desc_style is needed inside build_section_table; will be set after register_fonts
desc_style: ParagraphStyle | None = None


def main():
    global desc_style
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(Path.home() / "Desktop" / "polymetl_markets_full_dictionary.pdf"),
    )
    parser.add_argument("--host",     default=os.getenv("POLYMETL_CLICKHOUSE_HOST", "localhost"))
    parser.add_argument("--port",     type=int, default=int(os.getenv("POLYMETL_CLICKHOUSE_PORT", "9000")))
    parser.add_argument("--user",     default=os.getenv("POLYMETL_CLICKHOUSE_USER", "default"))
    parser.add_argument("--password", default=os.getenv("POLYMETL_CLICKHOUSE_PASSWORD", ""))
    parser.add_argument("--database", default=os.getenv("POLYMETL_CLICKHOUSE_DATABASE", "polymetl"))
    args = parser.parse_args()

    pdfmetrics.registerFont(UnicodeCIDFont(CJK))
    s = styles()
    desc_style = ParagraphStyle("desc", parent=s["body"], fontSize=8, leading=11, spaceAfter=0)

    print("connecting to ClickHouse and computing fill rates …")
    client = Client(host=args.host, port=args.port, user=args.user,
                    password=args.password, database=args.database)
    total, fills = compute_fill_rates(client)
    print(f"  total rows: {total:,}")

    # Build a {col_name: (src_key, ch_type, kind)} index from FIELDS + EXTRA_COLS
    info: dict[str, tuple[str, str]] = {}
    for name, src, ctype, _kind in FIELDS:
        info[name] = (src, ctype)
    for name, ctype in EXTRA_COLS:
        info[name] = ("(bookkeeping)", ctype)

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.6*cm,  bottomMargin=1.6*cm,
        title="polymetl.markets_full 数据字典 (128 列)",
        author="PolyMetl",
    )

    story = []
    story.append(Paragraph("polymetl.markets_full 数据字典", s["h1"]))
    story.append(Paragraph(
        f"数据快照：{total:,} 行（已用 ReplacingMergeTree FINAL 去重）&nbsp;|&nbsp; 列数：128 &nbsp;|&nbsp; "
        f"Gamma API 抓取时间：见 fetched_at 列。"
        f"&nbsp; 覆盖率定义：String 非空、Array 非空、Nullable(DateTime) 非 NULL、数值非 0。"
        f"零值未必代表「缺失」——例如 outcome_prices=[1,0] 时第二个元素是真实的 0。",
        s["caption"],
    ))
    story.append(Paragraph(
        "本字典按语义分组排列（共 14 节）。每节给出列名、ClickHouse 类型、原始 Gamma API 字段名、"
        "覆盖率统计、中文说明。配套全量 CSV 见桌面 polymetl_markets_full.csv，列序与本表 §1–§14 一致。",
        s["body"],
    ))

    # --- Per-section tables ---
    seen = set()
    for sec_title, cols in SECTIONS:
        story.append(Paragraph(sec_title, s["h2"]))
        rows = []
        for col in cols:
            if col not in info:
                continue
            seen.add(col)
            src, ctype = info[col]
            rows.append({
                "col":  col,
                "type": ctype,
                "src":  src,
                "fill": fmt_pct(fills.get(col, 0.0)),
                "desc": DESCRIPTIONS.get(col, "（待补充）"),
            })
        story.append(build_section_table(rows))

    # Sanity: any column we forgot to put in a section?
    missing = sorted(set(info) - seen)
    if missing:
        story.append(Paragraph("十五、未分组(请检查) / Ungrouped", s["h2"]))
        rows = []
        for col in missing:
            src, ctype = info[col]
            rows.append({
                "col": col, "type": ctype, "src": src,
                "fill": fmt_pct(fills.get(col, 0.0)),
                "desc": DESCRIPTIONS.get(col, "（缺失说明）"),
            })
        story.append(build_section_table(rows))

    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(
        f"© 2026 PolyMetl 毕业论文项目。源 schema 定义：polymetl/src/gamma_full.py FIELDS 列表。"
        f"覆盖率统计直接 SELECT countIf(...) FROM polymetl.markets_full FINAL。",
        s["caption"],
    ))

    doc.build(story)
    size_kb = out_path.stat().st_size / 1024
    print(f"wrote {out_path}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
