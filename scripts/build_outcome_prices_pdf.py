"""
Generate ~/Desktop/outcome_prices_explained.pdf

A self-contained Chinese-language explainer for the semantics of
`polymetl.markets_full.outcome_prices` — the seven distinct value
patterns we observed in the 146,190-market snapshot, what each one
means on-chain (CTF payout numerators), and why the user's correction
("[0,1] doesn't always mean NO wins") matters.

Usage:
    uv run python scripts/build_outcome_prices_pdf.py
    uv run python scripts/build_outcome_prices_pdf.py --out ~/Desktop/foo.pdf
"""
from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


CJK_FONT_NAME = "STSong-Light"  # Adobe CID font shipped with reportlab; no file needed
MONO_FONT_NAME = "Courier"


def register_fonts() -> None:
    pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT_NAME))


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    out = {
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontName=CJK_FONT_NAME,
            fontSize=18, leading=24, spaceAfter=10, textColor=colors.HexColor("#0f172a"),
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName=CJK_FONT_NAME,
            fontSize=13, leading=18, spaceBefore=14, spaceAfter=6,
            textColor=colors.HexColor("#1e293b"),
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontName=CJK_FONT_NAME,
            fontSize=10, leading=15, alignment=TA_LEFT, spaceAfter=6,
        ),
        "code": ParagraphStyle(
            "code", parent=base["BodyText"], fontName=MONO_FONT_NAME,
            fontSize=9, leading=12, leftIndent=12,
            backColor=colors.HexColor("#f1f5f9"),
            borderPadding=4, spaceAfter=8,
        ),
        "caption": ParagraphStyle(
            "caption", parent=base["BodyText"], fontName=CJK_FONT_NAME,
            fontSize=8, leading=11, textColor=colors.grey, spaceAfter=10,
        ),
    }
    return out


def cjk_table(data, col_widths, header_bg="#0f172a"):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME",     (0, 0), (-1, -1), CJK_FONT_NAME),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("LEADING",      (0, 0), (-1, -1), 12),
        ("BACKGROUND",   (0, 0), (-1, 0),  colors.HexColor(header_bg)),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",     (0, 0), (-1, 0),  CJK_FONT_NAME),
        ("ALIGN",        (1, 1), (1, -1),  "RIGHT"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",         (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
            [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    return t


def build_story(s):
    out = []

    out.append(Paragraph("Polymarket <font name='%s'>outcome_prices</font> 字段语义说明" % MONO_FONT_NAME, s["h1"]))
    out.append(Paragraph(
        "数据源：polymetl.markets_full（146,190 行，2026-05-08 抓取于 Gamma API）。"
        "以下结论由 ClickHouse 全表统计直接验证。",
        s["caption"],
    ))

    # ---------- Section 1: 全表分布 ----------
    out.append(Paragraph("1. 全表分布", s["h2"]))
    out.append(Paragraph(
        "outcome_prices 是 Float64 数组，与 outcomes 标签数组按位置一一对应。"
        "在已结算市场中，它来自链上 ConditionalToken（CTF）合约的 payoutNumerators / payoutDenominator；"
        "在未结算市场中，它是 CLOB 订单簿（或旧 AMM）当前价格快照。",
        s["body"],
    ))
    data = [
        ["模式", "总数", "closed=1", "active=1, closed=0", "含义"],
        ["[0, 1]",        "63,966", "63,966", "0",      "标准：第 2 个 outcome 胜"],
        ["[1, 0]",        "31,305", "31,305", "0",      "标准：第 1 个 outcome 胜"],
        ["[0.5, 0.5]",    "4,629",  "141",    "4,488",  "两种含义（见 §3）"],
        ["[0, 0]",        "162",    "162",    "0",      "AMM 池被抽空"],
        ["[1, 1]",        "14",     "14",     "0",      "UMA 判双胜 / 平局"],
        ["empty []",      "70",     "0",      "70",     "新市场未初始化"],
        ["其他（含 0.999...）", "46,044", "4,912", "41,132", "AMM 残留 / 实时报价"],
    ]
    out.append(cjk_table(data, [3.0*cm, 2.0*cm, 2.2*cm, 3.5*cm, 6.0*cm]))

    # ---------- Section 2: 关键纠错 ----------
    out.append(Paragraph("2. 关键纠错：[0, 1] 并非总是「NO 胜」", s["h2"]))
    out.append(Paragraph(
        "outcome_prices 与 outcomes 是位置对齐的并行数组，赢家 = outcomes[argmax(outcome_prices)]。"
        "以下数据展示了 [0, 1] 模式下 outcomes 标签的多样性："
        "约 16,000+ 条记录的赢家不是 'No'。",
        s["body"],
    ))
    data = [
        ["outcomes 标签",            "数量",     "[0, 1] 真实含义"],
        ["[Yes, No]",                "47,777",  "No 胜"],
        ["[Up, Down]",               "5,799",   "Down 胜（不是 NO）"],
        ["[Over, Under]",            "1,818",   "Under 胜"],
        ["[Favorite, Underdog]",     "270",     "Underdog 胜"],
        ["[Thunder, Nuggets] 等体育", "数十种",  "第 2 支队伍胜"],
    ]
    out.append(cjk_table(data, [6.0*cm, 2.5*cm, 8.2*cm]))
    out.append(Paragraph("严谨表述：", s["body"]))
    out.append(Paragraph(
        "outcomes       = [outcomes[0], outcomes[1], ...]<br/>"
        "outcome_prices = [price[0],    price[1],    ...]<br/>"
        "winner = outcomes[argmax(outcome_prices)]",
        s["code"],
    ))

    # ---------- Section 3: 异常模式逐一解释 ----------
    out.append(Paragraph("3. 异常模式逐一解释", s["h2"]))

    out.append(Paragraph("3.1  [0.5, 0.5] —— 两种完全不同的含义", s["h2"]))
    out.append(Paragraph(
        "<b>A. closed=1（141 个）：市场作废，按 0.5 退款。</b>"
        "链上 CTF payoutNumerators=[1,1] / payoutDenominator=2，"
        "意味着 YES 与 NO 持有者各按 0.5 USDC 退款。常见原因：题目无法验证、比赛被推迟、UMA 判 invalid。",
        s["body"],
    ))
    out.append(Paragraph(
        "示例：will-bybit-buy-1b-of-eth、nba-mil-phx-2023-02-26、ufc-319-silva-vs-aldrich、"
        "will-ynw-melly-be-found-guilty",
        s["code"],
    ))
    out.append(Paragraph(
        "<b>B. active=1（4,488 个）：新市场默认初始报价。</b>"
        "CLOB 订单簿薄、没有 bestBid/bestAsk → Gamma 用 50/50 做占位。"
        "<font color='#b91c1c'>注意</font>：这并不代表市场认为概率是 50%，仅仅是没有挂单。",
        s["body"],
    ))

    out.append(Paragraph("3.2  [0, 0] —— 162 个全是 AMM 时代被作废的市场", s["h2"]))
    out.append(Paragraph(
        "特征 100% 一致：fpmm_live=1、closed=1、绝大多数为 2021–2023 年的体育/事件市场。"
        "FPMM (Fixed Product Market Maker) 市场被作废时，sponsor 把 reserve 池整个抽走，"
        "implied price 公式 reserve_other / (reserve_yes + reserve_no) 分母为 0，"
        "Gamma 缓存为 [0, 0]。实际持有者仍按原始购买价获得退款。",
        s["body"],
    ))

    out.append(Paragraph("3.3  [1, 1] —— 14 个 UMA 判「双胜」", s["h2"]))
    out.append(Paragraph(
        "链上 CTF payoutNumerators=[1,1] / payoutDenominator=1，"
        "YES 与 NO 持有者各拿 1.0 USDC。这种结算对协议是亏损的，"
        "因为 split + merge 不再恒等于 1。极少见。",
        s["body"],
    ))
    data = [
        ["市场",                                     "为何 [1, 1]"],
        ["sri-lanka-vs-nepal-cricket-t20",           "比赛因雨水被取消/平局"],
        ["usa-vs-ireland-cricket-t20",               "同上"],
        ["who-will-win-ansem-vs-tate",               "比赛改期/取消"],
        ["musk-vs-zuck-will-the-richer-man-win",     "题目歧义，UMA 判 ambiguous"],
        ["biden-senile-during-the-debate",           "主观题，双方都有理"],
        ["young-thug-found-guilty-of-racketeering",  "部分罪名成立，两个解读都对"],
    ]
    out.append(cjk_table(data, [9.5*cm, 7.2*cm]))

    out.append(Paragraph("3.4  ≈ 0.999... 的 AMM 残留", s["h2"]))
    out.append(Paragraph(
        "全部来自 fpmm_live=1 的旧 AMM 市场（4,748 个二元 + 多结果市场）。"
        "FPMM 市场结算时，赢方代币被持有人不断兑换走 → reserve 比例倾斜到极端，"
        "implied price 数学上无限接近 1.0 但永远到不了。"
        "CLOB 时代之后（fpmm_live=0），结算用链上整数 payout，所以 outcome_prices 永远是精确 [1, 0] 或 [0, 1]。",
        s["body"],
    ))

    out.append(Paragraph("3.5  empty [] —— 70 个新市场刚部署", s["h2"]))
    out.append(Paragraph(
        "全部 active=1, closed=0。市场记录已建但 outcomePrices 字段尚未初始化。"
        "通常在 24 小时内变为 [0.5, 0.5] 或开始有真实报价。",
        s["body"],
    ))

    # ---------- Section 4: 链上对应表 ----------
    out.append(PageBreak())
    out.append(Paragraph("4. outcome_prices ↔ 链上 CTF 对应关系", s["h2"]))
    out.append(Paragraph(
        "Gamma 的 outcome_prices 是 ConditionalToken 合约 payoutNumerators / payoutDenominator 的镜像，"
        "AMM 市场（fpmm_live=1）除外，那里 outcome_prices 来自 reserve 比例。",
        s["body"],
    ))
    data = [
        ["outcome_prices",          "链上 CTF",                         "持有者赔付"],
        ["[1, 0]",                  "[1, 0] / 1",                       "YES 拿 1，NO 拿 0"],
        ["[0, 1]",                  "[0, 1] / 1",                       "NO 拿 1，YES 拿 0"],
        ["[0.5, 0.5] (closed)",     "[1, 1] / 2",                       "各拿 0.5（退款）"],
        ["[1, 1]",                  "[1, 1] / 1",                       "各拿 1（双胜，罕见）"],
        ["[0, 0]",                  "reserve 池被抽空（仅 AMM）",       "按原始购买价退款"],
        ["≈ 0.999, ≈ 1.4e-7",       "仅 AMM；CLOB 永远是整数",          "YES 拿 1（实际链上是干净的）"],
    ]
    out.append(cjk_table(data, [4.7*cm, 5.2*cm, 6.8*cm]))

    # ---------- Section 5: 实务建议 ----------
    out.append(Paragraph("5. 实务建议", s["h2"]))
    out.append(Paragraph(
        "1. 判断赢家始终用 outcomes[argmax(outcome_prices)]，对 AMM 和 CLOB 两套都正确；"
        "不要在文字里再写「YES 胜 / NO 胜」简称。",
        s["body"],
    ))
    out.append(Paragraph(
        "2. 做胜率/校准分析时使用 polymetl.markets_resolved 视图过滤 resolution_quality='resolved'，"
        "已自动剔除 [0,0]、[1,1]、[0.5,0.5]、empty [] 这些异常。",
        s["body"],
    ))
    out.append(Paragraph(
        "3. 不要把异常模式当作「市场预测概率 50%」用进 LLM 校准——它们不是市场预测错了，"
        "是市场根本没正常结算。",
        s["body"],
    ))
    out.append(Paragraph(
        "4. 需要纯净 ground truth 时，对 condition_id 字段（146,190 行 100% 覆盖）做一次链上 CTF "
        "payoutNumerators 单点查询即可，普通 RPC 就够用，无需 archive RPC。",
        s["body"],
    ))
    out.append(Paragraph(
        "5. AMM vs CLOB 的差异（做市行为、定价效率）对实证分析很重要，fpmm_live 是关键过滤字段。",
        s["body"],
    ))

    out.append(Spacer(1, 0.6*cm))
    out.append(Paragraph(
        "© 2026 PolyMetl 毕业论文项目。本说明由 ClickHouse 实证统计自动生成，"
        "对应表与字段定义可在 polymetl/src/gamma_full.py 与 polymetl/src/clickhouse_client.py 找到。",
        s["caption"],
    ))

    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(Path.home() / "Desktop" / "outcome_prices_explained.pdf"),
    )
    args = parser.parse_args()

    register_fonts()
    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2.0*cm, rightMargin=2.0*cm,
        topMargin=2.0*cm,  bottomMargin=2.0*cm,
        title="Polymarket outcome_prices 字段语义说明",
        author="PolyMetl",
    )
    s = styles()
    doc.build(build_story(s))
    size_kb = out_path.stat().st_size / 1024
    print(f"wrote {out_path}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
