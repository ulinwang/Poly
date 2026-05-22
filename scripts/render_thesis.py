"""Render the graduation thesis to a Word document.

Reproducible single source of truth for the thesis prose. Run:

    uv run python scripts/render_thesis.py \
        --out ~/Desktop/大语言模型驱动智能体的行为模拟研究——以Polymarket预测市场为例.docx

Organisation follows the seven academic elements requested by the
author: 研究背景 / 研究问题 / 研究方法 / 研究对象 / 实验过程 /
实验细节 / 实验结论. The body deliberately contains no software
version numbers and no engineering-process vocabulary — every claim is
phrased as a research idea, a datum, an analysis, or a conclusion.

All quantitative claims trace to committed artifacts under
docs/v13/ and output/v13/ (see docs/v13/RESULTS_*.md).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FIG_DIR = Path(__file__).resolve().parent.parent / "docs" / "v13" / "figures"
TBL_DIR = Path(__file__).resolve().parent.parent / "docs" / "v13" / "tables"


def _load_csv_rows(name, fmt=None):
    """Read a CSV from docs/v13/tables/ and return rows ready for
    three_line_table; optionally format numeric cells via `fmt` dict
    mapping column-name → format string."""
    import csv
    p = TBL_DIR / name
    rows = []
    with p.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out = []
            for k, v in row.items():
                if fmt and k in fmt:
                    try:
                        v = fmt[k] % float(v)
                    except (TypeError, ValueError):
                        pass
                out.append(v)
            rows.append(out)
    return rows


def _load_action_mix_rows():
    return _load_csv_rows("table6_action_mix.csv",
        fmt={a: "%.1f" for a in ["限价单", "市价单", "撤单", "不操作",
                                  "拆分", "合并", "声明信念"]})


def _load_b1_markets_rows():
    rows = _load_csv_rows("table7_b1_markets.csv")
    # shorten the slug for display
    short = {
        "dogecoin-above-0pt34-on-january-17": "狗狗币>0.34",
        "nba-por-mia-2025-01-21": "NBA POR-MIA",
        "will-yamand-orsi-win-the-2024-uruguay-presidential-election": "乌拉圭大选",
        "nba-gsw-min-2025-01-15": "NBA GSW-MIN",
        "will-cducsu-and-spd-form-the-next-german-government": "德国组阁",
        "will-xrp-dip-to-1pt50-in-august-343-253-666-332-591": "XRP<1.50",
        "nba-phx-ind-2025-01-04": "NBA PHX-IND",
        "will-the-price-of-bitcoin-be-less-than-78000-on-mar-28": "BTC<78000",
        "will-xrp-dip-to-1pt00-in-march": "XRP<1.00",
        "will-elon-musk-buy-msnbc-before-april-2025": "马斯克买MSNBC",
    }
    for r in rows:
        r[0] = short.get(r[0], r[0][:14])
    return rows


def _load_archetype_pnl_rows():
    return _load_csv_rows("table8_b3_archetype_pnl.csv")


def _load_scale_rows():
    """table9_scale.csv → display rows for the scale experiment."""
    rows = []
    for r in _load_csv_rows("table9_scale.csv"):
        n, em, es, vol, notion, fills, cancel, spread = r
        rows.append([
            f"{int(float(n))}",
            f"{float(em):.3f} ± {float(es):.3f}",
            f"{float(vol):.4f}",
            f"{float(notion):,.0f}",
            f"{float(fills):.0f}",
            f"{float(cancel):.1f}",
        ])
    return rows


def _load_tick_rows():
    """table10_tick.csv → display rows for the tick-horizon experiment."""
    rows = []
    for r in _load_csv_rows("table10_tick.csv"):
        t, em, es, vol, acts, fills, spread = r
        rows.append([
            f"{int(float(t))}",
            f"{float(em):.3f} ± {float(es):.3f}",
            f"{float(vol):.4f}",
            f"{float(acts):.0f}",
            f"{float(fills):.0f}",
        ])
    return rows


def _load_open_rows():
    """table11_open.csv → display rows for the open-market preview."""
    rows = []
    for r in _load_csv_rows("table11_open.csv"):
        seed, start, end, drift, vol, fills, pnl = r
        rows.append([
            f"种子 {int(float(seed))}",
            f"{float(start):.3f}",
            f"{float(end):.3f}",
            f"{float(drift):+.3f}",
            f"{float(vol):.4f}",
            f"{int(float(fills))}",
        ])
    return rows


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


# --- NJU 2026 thesis format spec (docs/v13/THESIS_FORMAT_SPEC.md) ---
SONG = "宋体"          # 正文中文
HEI = "黑体"           # 标题中文
KAI = "楷体_GB2312"     # 摘要中文 / 封面信息行
LATIN = "Times New Roman"  # 正文西文与数字
PT_BODY = 12           # 小四
PT_H1 = 16             # 三号(章/参考文献/致谢/附录)
PT_H2 = 14             # 四号(节)
PT_ABS_TITLE = 18      # 摘要页标题
IND_FIRST = Cm(0.85)   # 正文首行缩进 ≈ 2 字符
IND_HANG = Cm(0.76)    # 参考文献悬挂缩进


def _set_run(run, *, ea=SONG, latin=LATIN, size=PT_BODY, bold=False):
    """Apply Chinese + Western font, size, weight to a run, including
    the w:eastAsia attribute python-docx does not set by default."""
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = latin
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.append(rf)
    rf.set(qn("w:ascii"), latin)
    rf.set(qn("w:hAnsi"), latin)
    rf.set(qn("w:eastAsia"), ea)


def _page_setup(doc):
    for s in doc.sections:
        s.page_width = Cm(21.0)
        s.page_height = Cm(29.7)
        s.top_margin = Cm(2.54)
        s.bottom_margin = Cm(2.54)
        s.left_margin = Cm(3.17)
        s.right_margin = Cm(3.17)
        s.header_distance = Cm(1.5)
        s.footer_distance = Cm(1.75)


def h1(doc, text):
    """一级标题。章/参考文献/致谢/附录:黑体三号居中;
    摘要页标题:楷体_GB2312 18pt 居中。"""
    is_abs = ("摘要" in text) or (text.strip().lower() == "abstract")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(12)
    r = p.add_run(text)
    if is_abs:
        _set_run(r, ea=KAI, size=PT_ABS_TITLE, bold=True)
    else:
        _set_run(r, ea=HEI, size=PT_H1, bold=True)
    return p


def h2(doc, text):
    """二级标题:黑体四号居左,段前约 0.28 cm。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Cm(0.28)
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run(text)
    _set_run(r, ea=HEI, size=PT_H2, bold=True)
    return p


def para(doc, text, indent=True):
    """正文:宋体/Times New Roman 小四,1.5 倍行距,两端对齐,
    首行缩进 ≈2 字符。"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    if indent:
        pf.first_line_indent = IND_FIRST
    pf.line_spacing = 1.5
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run(text)
    _set_run(r, ea=SONG, size=PT_BODY)
    return p


def apara(doc, text, lead=None):
    """摘要正文:楷体 12pt,1.5 倍行距。`lead` 为加粗引导词
    (如“摘要：”“关键词：”)。"""
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.5
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    if lead:
        r0 = p.add_run(lead)
        _set_run(r0, ea=KAI, size=PT_BODY, bold=True)
    r = p.add_run(text)
    _set_run(r, ea=KAI, size=PT_BODY)
    return p


def bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.line_spacing = 1.5
    r = p.add_run(text)
    _set_run(r, ea=SONG, size=PT_BODY)
    return p


def _set_cell_border(cell, **edges):
    """Set individual cell borders. edges like top={'sz':12,'val':'single'}."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcB = tcPr.find(qn("w:tcBorders"))
    if tcB is None:
        tcB = OxmlElement("w:tcBorders")
        tcPr.append(tcB)
    for edge in ("top", "left", "bottom", "right"):
        spec = edges.get(edge)
        el = tcB.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tcB.append(el)
        if spec is None:
            el.set(qn("w:val"), "nil")
        else:
            el.set(qn("w:val"), spec.get("val", "single"))
            el.set(qn("w:sz"), str(spec.get("sz", 8)))
            el.set(qn("w:color"), spec.get("color", "000000"))


# table number is auto-incremented; caption goes ABOVE (academic style)
_TBL = {"n": 0}
_FIG = {"n": 0}


def three_line_table(doc, title, headers, rows, widths_cm=None):
    """Academic three-line (三线表) table. Caption above; only the
    table top rule, header-bottom rule, and table bottom rule are
    drawn — no vertical or inner horizontal lines."""
    _TBL["n"] += 1
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cr = cap.add_run(f"表 {_TBL['n']}  {title}")
    _set_run(cr, ea=SONG, size=10.5, bold=True)

    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.alignment = 1  # center
    thick = {"sz": 14, "val": "single"}
    thin = {"sz": 6, "val": "single"}
    n_rows = 1 + len(rows)
    for ci, htext in enumerate(headers):
        c = t.rows[0].cells[ci]
        c.text = str(htext)
        for para_ in c.paragraphs:
            para_.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para_.paragraph_format.line_spacing = 1.25
            for rr in para_.runs:
                _set_run(rr, ea=SONG, size=10, bold=True)
        _set_cell_border(c, top=thick, bottom=thin)
    for ri, row in enumerate(rows, 1):
        for ci, v in enumerate(row):
            c = t.rows[ri].cells[ci]
            c.text = str(v)
            for para_ in c.paragraphs:
                para_.alignment = WD_ALIGN_PARAGRAPH.CENTER
                para_.paragraph_format.line_spacing = 1.25
                for rr in para_.runs:
                    _set_run(rr, ea=SONG, size=10)
            bottom = thick if ri == n_rows - 1 else None
            _set_cell_border(c, bottom=bottom)
    if widths_cm:
        for r in t.rows:
            for ci, w in enumerate(widths_cm):
                r.cells[ci].width = Cm(w)
    doc.add_paragraph()
    return t


def figure(doc, png_name, title, width_cm=13.5):
    """Embed a figure centered with a Chinese caption BELOW it."""
    _FIG["n"] += 1
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(FIG_DIR / png_name), width=Cm(width_cm))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cr = cap.add_run(f"图 {_FIG['n']}  {title}")
    _set_run(cr, ea=SONG, size=10.5, bold=True)
    doc.add_paragraph()


def caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text)
    r.italic = True
    r.font.size = Pt(10.5)


def pagebreak(doc):
    doc.add_page_break()


REFERENCES = [
    "[1] Yang Y, Zhang Y, Wu M, et al. TwinMarket: A Scalable Behavioral and Social Simulation for Financial Markets. 2025.",
    "[2] Gomez-Cram R, Hasan I, Park J. Predator and Prey: The Hidden User Role Dynamics of Decentralized Markets. ICIS, 2026.",
    "[3] Zhao Z, Gao J, Xu D, et al. CompeteAI: Understanding the Competition Dynamics in Large Language Model-based Agents. 2024.",
    "[4] Li N, Gao C, Li M, et al. Large Language Model-Empowered Agents for Simulating Macroeconomic Activities. 2024.",
    "[5] Yao S, Zhao J, Yu D, et al. ReAct: Synergizing Reasoning and Acting in Language Models. ICLR, 2023.",
    "[6] Park J S, O'Brien J C, Cai C J, et al. Generative Agents: Interactive Simulacra of Human Behavior. UIST, 2023.",
    "[7] Baqaee D, Rubbo E. Micro Propagation and Macro Aggregation. Annual Review of Economics, 2023.",
    "[8] Glosten L R, Milgrom P R. Bid, Ask and Transaction Prices in a Specialist Market with Heterogeneously Informed Traders. Journal of Financial Economics, 14(1):71–100, 1985.",
    "[9] Kyle A S. Continuous Auctions and Insider Trading. Econometrica, 53(6):1315–1335, 1985.",
    "[10] Wolfers J, Zitzewitz E. Prediction Markets. Journal of Economic Perspectives, 18(2):107–126, 2004.",
    "[11] Hommes C. Behavioral Rationality and Heterogeneous Expectations in Complex Economic Systems. 2013.",
    "[12] LeBaron B. Agent-Based Computational Finance. Handbook of Computational Economics, 2:1187–1233, 2006.",
    "[13] Hennig C. Cluster-wise Assessment of Cluster Stability. Computational Statistics & Data Analysis, 52(1):258–271, 2007.",
    "[14] Manela A, Moreira A. News Implied Volatility and Disaster Concerns. Journal of Financial Economics, 123(1):137–162, 2017.",
    "[15] Polymarket Documentation. Central Limit Order Book API Reference. https://docs.polymarket.com/, accessed 2026-05.",
    "[16] Gnosis ConditionalTokens v1.0 Specification. https://docs.gnosis.io/conditionaltokens/, accessed 2026-05.",
]


# ----------------------------------------------------------------------
# document body
# ----------------------------------------------------------------------


def _cover_line(doc, label, value, label_w=4.5, value_w=8.5):
    """A 封面 info line: label aligned right, value left, both 16pt 楷体_GB2312."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    r1 = p.add_run(f"{label:>4}".replace(" ", "　") + "   ")
    _set_run(r1, ea=KAI, size=16, bold=True)
    r2 = p.add_run(str(value))
    _set_run(r2, ea=KAI, size=16, bold=False)


def cover_page(doc):
    """南京大学本科毕业论文封面。"""
    # 顶部空白
    for _ in range(3):
        doc.add_paragraph()
    # 大标题
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(36)
    r = p.add_run("本 科 毕 业 论 文")
    _set_run(r, ea=SONG, size=26, bold=True)
    # 信息行
    _cover_line(doc, "学    院", "信息管理学院")
    _cover_line(doc, "专    业", "信息管理与信息系统")
    _cover_line(doc, "题    目",
                "大语言模型驱动智能体的行为模拟研究——以 Polymarket 预测市场为例")
    _cover_line(doc, "年    级", "2022     学    号   221820328")
    _cover_line(doc, "学生姓名", "王 友 林")
    _cover_line(doc, "指导教师", "颜 嘉 麒     职    称   教  授")
    _cover_line(doc, "提交日期", "2026 年 6 月")
    pagebreak(doc)


def build(doc: Document) -> None:
    # ---------- 封面 ----------
    cover_page(doc)
    # ---------- 摘要 ----------
    h1(doc, "中文摘要")
    apara(doc,
        "本研究面向 Polymarket 去中心化预测市场,构建一个由大语言模型"
        "驱动的多智能体仿真工具,并以此检验大语言模型驱动的智能体能否"
        "模拟真实交易者的行为。工具以真实早期成交导出市场参数,以一百"
        "一十九万个真实钱包的链上历史刻画参与者画像,以连续竞价订单簿"
        "撮合交易,从而把真实市场转化为可受控、可复现、可干预的模拟"
        "环境。实验围绕五个研究问题展开:其一,在已关闭市场上比较智能体"
        "模拟出的交易者行为与真实数据;其二,改变智能体数量(10、20、"
        "50)考察规模的影响;其三,改变决策轮数(10、20、40)考察模拟"
        "时长的影响;其四,通过消融实验识别群体构造、信念机制、消息"
        "冲击和初始判断设定各自的作用;其五,在未关闭市场上运行预演,"
        "输出可在结算前阅读的价格区间与交易压力。",
        lead="摘要：")
    apara(doc,
        "研究得到以下结论。智能体能复现结构上可信的交易者行为与市场"
        "微观结构,但在初始价格已含较强信息的市场上不会自行把价格推向"
        "真实结果。增加智能体数量主要带来成比例的流动性,不改变价格"
        "结构;延长模拟时长只增加成比例的交易活动,价格在约二十轮后"
        "趋于稳定,工具具有内在的收敛性质。消融实验显示:为智能体引入"
        "一个明确、可跨轮持久的信念状态,显著降低了无意义地反复挂单又"
        "撤单的行为;基于行为特征的聚类相对随机群体不产生可检出的市场"
        "差异;一次外生消息冲击主要通过既有资金流动路径放大交易量;而"
        "初始主观判断的生成方式则决定价格是否系统性偏离真实方向,本文"
        "定位并修正了其中一处方法缺陷。在未关闭市场上,智能体模拟出的"
        "行为能汇聚成多次模拟之间一致的预先判断。上述发现说明,该工具"
        "可用于已关闭市场的复现实验与交易者行为分析,也可用于未关闭"
        "市场的事前情景分析;但其价值在于刻画行为与微观结构的过程,"
        "而非替代真实市场做最终结算方向的预测。")
    apara(doc, "大语言模型;多智能体仿真;预测市场;行为金融;信息聚合",
          lead="关键词：")

    pagebreak(doc)
    h1(doc, "Abstract")
    para(doc,
        "This thesis builds a large-language-model-driven multi-agent "
        "simulation tool for the Polymarket decentralized prediction "
        "market and uses it to test whether LLM-driven agents can "
        "simulate the behaviour of real traders. The tool derives market "
        "parameters from early real trades, builds participant profiles "
        "from the on-chain history of 1.19 million wallets, and matches "
        "agent orders on a continuous double-auction order book. The "
        "experiments address five research questions: comparing simulated "
        "trader behaviour with real data on closed markets; varying the "
        "agent count (10, 20, 50) to study scale; varying the decision "
        "horizon (10, 20, 40 rounds) to study simulation length; ablating "
        "population construction, belief state, message shock, and "
        "initial-prior design; and running a pre-close simulation on an "
        "open market for readable pre-settlement evidence.")
    para(doc,
        "Findings are as follows. Agents reproduce structurally credible "
        "trader behaviour and market microstructure, but do not by "
        "themselves push price toward the true outcome on markets whose "
        "opening price already carries information. Adding agents mainly "
        "scales liquidity proportionally without changing price structure; "
        "extending the horizon only adds proportional trading activity, "
        "with price settling after about twenty rounds, indicating an "
        "intrinsic convergence property. Ablations show that an explicit, "
        "persistent belief state markedly reduces meaningless order churn; "
        "behavioural-cluster populations show no detectable market "
        "difference over a random population; an information shock "
        "amplifies volume along existing flow paths; and the "
        "initial-prior sampling method governs whether price drifts "
        "systematically away from the truth, a flaw identified and fixed "
        "here. On an open market, simulated behaviour converges to a "
        "pre-close judgement consistent across seeds. The tool thus serves "
        "as a replay and behaviour-analysis environment for closed markets "
        "and a scenario tool for open markets; its value lies in "
        "characterising behaviour and microstructure, not in replacing the "
        "real market as an end-to-end settlement predictor.")
    para(doc,
        "Keywords: large language model; multi-agent simulation; "
        "prediction market; behavioral finance; information aggregation",
        indent=False)

    # ---------- 第一章 研究背景 ----------
    pagebreak(doc)
    h1(doc, "第一章  研究背景")
    para(doc,
        "预测市场是一种以价格聚合分散信息的机制:参与者就某一未来事件买卖"
        "二元结果合约,均衡价格被广泛解读为该事件发生概率的市场共识估计。"
        "相较问卷或专家判断,预测市场因其参与者以真实资金承担风险而具有"
        "较强的激励相容性,长期被视为研究信息如何被群体聚合的天然实验场。")
    para(doc,
        "与此同时,大语言模型展现出在缺乏显式数值训练的情况下进行情境化"
        "推理与角色扮演的能力,这使得以语言模型为决策核心、构造可控的人工"
        "市场参与者群体成为可能。已有研究在宏观经济活动、社会互动与竞争"
        "动态等场景中以语言模型智能体复现了若干定性现象。然而,将这类智能体"
        "置于一个具有真实撮合机制、真实参与者画像与真实结算结果的预测市场中,"
        "并以可证伪的方式检验其行为动力学,仍缺乏系统的实证工作。")
    para(doc,
        "本研究的动机在于:一方面,真实预测市场提供了带有客观结算标签的"
        "丰富行为数据,使得仿真可被严格校准与检验;另一方面,语言模型智能体"
        "的行为是否真实、其群体动力学是否由所假设的结构驱动、其结论在多大"
        "程度上可信,这些问题本身需要以实验方法回答,而非默认成立。明确"
        "仿真的有效性边界,与展示其能复现何种现象,具有同等的科学价值。")

    # ---------- 第二章 研究问题 ----------
    pagebreak(doc)
    h1(doc, "第二章  研究问题")
    para(doc,
        "本研究的核心是大语言模型驱动的智能体能否模拟真实交易者的"
        "行为。围绕这一核心,本文先建立一个能可控、可复现地模拟 "
        "Polymarket 真实市场的智能体仿真工具,再用它检验智能体模拟出"
        "的交易者行为在不同条件下的质量与稳定性。所谓“交易者行为”,"
        "在本文中指可被撮合环境记录与统计的具体动作:挂单、成交、"
        "持仓变化与最终损益,以及由这些动作聚合而成的市场层面结果"
        "——价格路径与价格发现。围绕这一核心,本文提出以下五个研究"
        "问题。")
    para(doc,
        "研究问题一(智能体能否模拟出真实交易者的行为):用多个"
        "智能体重新模拟已经关闭、且有明确结算结果的市场,智能体群体"
        "表现出的交易者行为——下单、成交、持仓、损益——以及由其聚合"
        "而成的价格路径与价格发现,与真实交易者留在市场上的数据有多"
        "接近?比较时不只看仿真终态是否落在正确一侧,还要看价格是否"
        "在仿真过程中朝真实结果方向移动。")
    para(doc,
        "研究问题二(智能体数量如何影响行为模拟):固定同一个已关闭"
        "市场,把智能体数量从 10 个增加到 20 个、再到 50 个,模拟出的"
        "交易者行为与市场结构是否更接近真实,还是产生新的群体行为"
        "现象?这一问题考察交易量、撤单比例、价格波动、资金流网络与"
        "个体损益分布随规模的变化。")
    para(doc,
        "研究问题三(模拟时长如何影响行为模拟):固定智能体数量与"
        "其余全部参数,只把决策轮数从 10 轮增加到 20 轮、再到 40 轮,"
        "智能体模拟出的交易者行为随模拟时长如何演变——价格是趋于"
        "稳定,还是持续漂移?动作结构是否随轮数稳定?")
    para(doc,
        "研究问题四(哪些设计决定行为模拟的质量):智能体的哪些设计"
        "真正影响它模拟出的交易者行为?本文通过消融实验逐一改变群体"
        "构造方式、是否保留持久信念、是否注入外部消息,以及初始主观"
        "判断的生成方式,识别哪些设计改变行为或结果,哪些主要影响"
        "行为质量与解释性。")
    para(doc,
        "研究问题五(对未关闭市场能否给出预先结论):对尚未关闭的"
        "市场做智能体仿真,模拟出的交易者行为能否汇聚成一个有意义的"
        "预先判断——例如仿真价格区间、群体信念、净买卖压力与交易"
        "活跃度?多次模拟之间是否一致?这一部分不评价预测是否命中,"
        "而评价工具能否在结算前组织信息、暴露分歧并给出可观察的"
        "情景判断。")
    para(doc,
        "上述五问中,前四个问题使用已经关闭的市场,因此可以与真实"
        "结果比较;第五个问题使用未关闭市场,因此只输出预先判断与"
        "风险提示。所有比较均建立在一个先于任何处理估计的随机性"
        "基线之上(详见第三章),只有大于该基线的差异才被视为可"
        "识别的处理效应。第五章末同时说明本工具的适用边界:在初始"
        "价格已含较强信息时,工具的价值在于刻画行为与微观结构的"
        "过程,而非对最终结算方向做端到端的预测。")

    # ---------- 第三章 研究方法 ----------
    pagebreak(doc)
    h1(doc, "第三章  研究方法")

    h2(doc, "一、总体设计")
    para(doc,
        "本研究构造一个连续竞价的二元结果市场仿真:每个智能体在每一轮"
        "观察当前市场状态与自身持仓,通过结构化的交易动作(挂出限价单、"
        "按当前价立即成交、撤单、份额的拆分与合并,或不操作)与撮合环境"
        "交互;环境按“价格优先、时间优先”撮合,并即时更新买卖报价。"
        "所有可调参数均由真实数据以确定的方式导出;语言模型有一个控制"
        "其输出随机性的参数(此处称“决策温度”),本文将其设为零,使其"
        "尽量给出确定、可重复的回答,以最大化实验的可复现性。仿真的"
        "总体流程如下图所示。")
    figure(doc, "fig1_loop.png", "仿真总体流程", width_cm=15)

    h2(doc, "二、参与者画像的构造")
    para(doc,
        "参与者画像来自真实钱包的链上交易历史。本文在七个相互区分度较高"
        "的行为特征上刻画每个钱包:累计名义交易额、最大单一市场集中度、"
        "单位资金对应的市场广度、平均成交价、尾部极端价格交易占比、活跃"
        "时长与成交价波动。把全体钱包按这七个特征做聚类(即把行为相近的"
        "钱包归为一类),得到若干类,每一类称为一种“行为原型”,再据此"
        "抽样构造智能体群体。为评估这种聚类结构是否真的必要,本文同时"
        "构造两种对照群体:一种只复现这七个特征各自的总体分布、但打乱了"
        "类别结构;另一种完全均匀随机抽取。")
    para(doc,
        "为杜绝未来信息进入画像,所有特征严格只由目标事件开始之前的交易"
        "数据计算,聚类也只在“事件开始前”这一时点的数据上进行。聚类应分"
        "几类,由两条标准共同确定:一是类内紧凑、类间分离的程度(轮廓"
        "系数);二是对数据反复有放回地重新抽样后,同一类能否稳定地复现"
        "(以两个集合的重叠比例衡量,要求其中位数不低于 0.75[13])。"
        "仅当某一类数下每一类都稳定复现、且没有哪一类规模过小时,该类数"
        "才被采纳。")

    h2(doc, "三、初始主观判断的设定")
    para(doc,
        "每个智能体在交易开始前都有一个对结果的初始主观判断(下文称其"
        "“初始判断”)。它的平均值取自市场早期真实成交所反映的群体平均"
        "看法;它的不确定程度则与该参与者的历史预测准确率有关:历史越准,"
        "初始判断越集中。这一判断的取值必须落在 0 与 1 之间。本文的一项"
        "关键方法发现是:若用“先按正态分布随机取一个数,落在 0 到 1 之外"
        "就丢弃、重新取”的办法来生成它,当群体平均看法本身接近 0 或 1"
        "(即市场已较为确信)时,被丢弃的那一侧会使最终取到的数的平均值"
        "被系统性地抬高,从而让每个智能体都得到一个偏离群体看法、且方向"
        "一致的判断。本文改用一种取值天然落在 0 到 1 之间、且能精确保持"
        "目标平均值的分布来生成它,从而消除这一偏差;第六章与第七章给出"
        "量化证据。")

    h2(doc, "四、智能体每一轮收到的信息")
    para(doc,
        "为保证方法透明与可复现,这里逐项说明智能体在每一轮决策时"
        "实际看到的全部信息。给语言模型的输入分为两部分:一部分在整场"
        "仿真中固定不变,用于设定其身份与规则;另一部分每一轮重新填写,"
        "描述当前局势与它自己的状态。")
    para(doc,
        "固定不变的部分包含:(一)该智能体的行为画像,即用自然语言"
        "陈述的、来自其对应真实钱包的交易风格;(二)其风险偏好的取值"
        "说明;(三)本场市场要预测的问题原文、结算规则与结算日期;"
        "(四)它可以采取的全部动作及各自含义,以及必须遵守的硬约束"
        "——买入金额不得超过现金、卖出不得超过持仓、报价须落在 0.01 "
        "到 0.99 之间并对齐到该市场的最小报价单位、且任何时候都不被"
        "告知真实结果;(五)一句要求:在给出动作的同时,用一两句话以"
        "其身份口吻说明理由,并先设想“若价格继续上行或下行我将如何应对”,"
        "以促使其对自己将要承诺的价位负责,而非追涨杀跌。")
    para(doc,
        "智能体并不是自由生成一段文字后由研究者人工解释,而是必须从"
        "预先定义好的动作集合中选择一个动作,并给出结构化参数。这样做"
        "的好处是:每个决策都能被撮合系统执行,也能在事后被统计为"
        "价格、行为、资金流或损益指标。")
    three_line_table(doc, "智能体可执行的动作及含义",
        ["动作", "含义", "用于观察的问题"],
        [
            ["LIMIT", "在指定价格挂出买入或卖出订单", "是否愿意提供流动性,以及报价方向"],
            ["MARKET", "按当前盘口立即买入或卖出", "是否出现更强烈的即时交易意愿"],
            ["CANCEL", "撤销自己尚未成交的挂单", "是否存在反复挂单又撤单的行为"],
            ["HOLD", "本轮不交易", "是否倾向于观望或缺少可行动信息"],
            ["SPLIT", "把现金拆成一组“是/否”份额", "是否主动扩大可交易头寸"],
            ["MERGE", "把配对份额合并回现金", "是否主动收缩风险暴露"],
            ["UPDATE_BELIEF", "声明并保存当前对结果的概率判断", "信念是否稳定,以及是否减少无意义挂撤"],
        ],
        widths_cm=[2.6, 5.8, 5.8])
    para(doc,
        "每一轮重新填写的部分包含:(一)该智能体的初始主观判断及其"
        "不确定程度,并明确告知这只是起始看法、非真实结果;(二)当前"
        "两侧(“是”与“否”)的最优买价、最优卖价与中间价,以及最近三轮"
        "的“是”侧中间价序列;(三)市场已进行的时间占其总时长的比例;"
        "(四)它自己的现金、两侧持仓数量与挂在簿上的未成交订单数;"
        "(五)它最近若干轮的动作摘要,每条包含该轮的动作类型、方向、"
        "价格、金额、成交笔数与成交后“是”侧中间价,并附一句提示:把"
        "上一轮陈述的看法当作当前的基准,只在出现新信息时才修正,且"
        "不要仅为“清空重来”而撤掉已挂的单。")
    para(doc,
        "在上述基础记忆之外,本文引入一个明确的信念机制:智能体可在"
        "任一轮主动声明它当前对结果的概率判断与把握程度,这一声明被"
        "保留下来,并在之后各轮回填到它收到的信息中(包含设定于第几轮、"
        "距今几轮、当时的理由)。其动机在于:若只保留历史动作,语言"
        "模型每一轮都需从动作记录反推“我上一轮到底相信什么”,这一反推"
        "的不稳定被怀疑是无意义地反复挂单又撤单的来源之一;第六章给出检验。")

    h2(doc, "五、市场撮合环境")
    para(doc,
        "撮合环境实现一个标准的连续双向竞价订单簿,支持限价与市价委托、"
        "撤单、以及二元份额的拆分与合并,按价格-时间优先成交并阻止自成交。"
        "市场开始时的初始挂单由真实早期行情的价格、买卖价差与深度确定,"
        "交易费率与最小报价单位取自目标市场的真实参数。环境内部状态"
        "对智能体不可见,智能体只能通过上述动作与之交互;智能体也无法看到其他智能体各自做了什么,"
        "以贴近真实市场的匿名性。")

    # ---------- 第四章 研究对象 ----------
    pagebreak(doc)
    h1(doc, "第四章  研究对象")

    h2(doc, "一、为什么选择 Polymarket")
    para(doc,
        "研究对象为 Polymarket 去中心化预测市场及其真实参与者总体。"
        "Polymarket 以连续竞价订单簿撮合二元结果合约,事件结算后获胜"
        "结果合约价值归一、另一侧归零,为仿真提供了客观的结算标签。")
    para(doc,
        "选择 Polymarket 有三个原因。第一,每个二元市场都有明确的"
        "结算结果,因此可以比较仿真价格与真实结果之间的关系。第二,"
        "其订单簿、成交与钱包行为能够对应到可执行的市场环境,使 Agent "
        "的每一步交易都不是抽象选择,而是能被撮合、成交、撤销和结算。"
        "第三,平台包含体育、加密资产、政治与公共事件等不同题材,便于"
        "观察同一套 Agent 机制在不同市场上的表现是否一致。")
    para(doc,
        "参与者总体为一百一十九万个真实钱包的链上交易历史。其行为高度"
        "异质:既有极少数大额、跨市场分散的参与者,也有大量小额、集中于"
        "单一市场的参与者。本文不把这些钱包简单视为同质交易者,而是"
        "从事件发生前的交易行为中抽样和刻画 Agent,以尽量避免使用事件"
        "发生后的信息。")

    h2(doc, "二、已关闭市场与未关闭市场")
    para(doc,
        "本文使用三组市场。第一组是已关闭市场中的受控实验基底:Succession 第四季"
        "中“Roman Roy 是否会在季末成为 CEO”这一市场,真实结算为“否”,"
        "YES 侧起始中间价约为 0.155。选择它作为基底,是因为它是已结算的"
        "二元市场,事件前有足够的钱包行为可用于构造 Agent,且初始价格"
        "不在 0.5 附近,更容易检验 Agent 是否会把价格推向或推离真实结果。"
        "随机性、规模实验和消融实验都在同一基底市场上重复,从而保证每组"
        "实验只改变一个主要因素。")
    para(doc,
        "第二组是已关闭市场的十市场面板,用于观察基底市场中发现的问题是否也出现在"
        "其他题材与其他起始价格的市场中。十个市场按固定规则选出:均为"
        "已结算二元市场;成交量介于 5000 美元至 500 万美元之间;事件前"
        "至少有 30 个可用钱包;真实结果保持“是/否”各五个;题材覆盖"
        "加密资产、体育比赛、选举与公共事件。这样选取不是为了挑选"
        "最有利的例子,而是为了同时包含高起点、低起点和接近中间价的"
        "市场,检查仿真是否存在一致的方向偏差。")
    para(doc,
        "第三组是未关闭市场,用于预演式仿真。本文的工程配置以 SpaceX "
        "Flight Test 11 相关市场为例,在市场尚未结算时构造 Agent 群体并"
        "运行交易。由于没有真实结算标签,这一组实验不计算终态正确率或"
        "结算后损益,而是输出仿真价格区间、Agent 信念分布、净买卖压力、"
        "交易活跃度和主要不确定性来源,用于说明工具能够在结算前提供"
        "结构化的预先结论。")
    three_line_table(doc, "市场选择原则与用途",
        ["市场集合", "包含市场", "选择理由", "在论文中的用途"],
        [
            ["已关闭基底市场", "Roman Roy 是否成为 CEO", "已结算;事件前钱包充足;起点约 0.155", "规模实验和消融实验"],
            ["已关闭十市场面板", "5 个真实为是,5 个真实为否", "成交量适中;至少 30 个钱包;题材和起点分散", "与真实结算做跨市场比较"],
            ["未关闭预演市场", "SpaceX Flight Test 11 相关市场", "仍在交易;可观察结算前信息", "输出预先结论和不确定性提示"],
        ],
        widths_cm=[2.6, 4.0, 4.4, 4.0])
    three_line_table(doc, "十市场面板的导出参数与事件前钱包池规模",
        ["市场", "结果", "开盘日期", "群体先验", "轮数", "tick", "钱包数", "簇数"],
        _load_b1_markets_rows(),
        widths_cm=[2.8, 1.4, 2.4, 1.8, 1.4, 1.6, 2.0, 1.4])

    h2(doc, "三、事件前参与者画像")
    para(doc,
        "在只使用事件发生前数据的前提下,基底市场可用的参与者群体经标准化特征重新聚类"
        "后稳健的类数为四,而非不做时间限制时表面上得到的五。这一差异并非"
        "细枝末节:它直接改变了用于刻画群体的原型,并在第六章的群体结构"
        "对照中产生实质后果。本文在附录中给出最终采用的四类行为原型的"
        "数据画像,并强调其为描述性分类。")

    # ---------- 第五章 实验过程 ----------
    pagebreak(doc)
    h1(doc, "第五章  实验过程")
    para(doc,
        "本章把实验设计与比较指标一次性说明清楚。全部实验围绕第二章的"
        "五个研究问题组织:前四个问题使用已经关闭、有真实结算结果的"
        "市场,因而可以把智能体模拟出的交易者行为与真实数据对照;第五"
        "个问题使用尚未关闭的市场,只输出结算前的预先判断。下表把五个"
        "研究问题与对应的实验模块一一列出。")
    three_line_table(doc, "研究问题与实验模块对照",
        ["研究问题", "实验模块", "市场状态", "核心设置"],
        [
            ["一 能否模拟真实交易者行为", "已关闭市场复现", "已关闭",
             "十市场面板;n=30"],
            ["二 智能体数量的影响", "规模实验", "已关闭",
             "Roman Roy;n=10/20/50;各三种子"],
            ["三 模拟时长的影响", "时长实验", "已关闭",
             "Roman Roy;n=20;10/20/40 轮;各三种子"],
            ["四 哪些设计决定模拟质量", "消融实验", "已关闭",
             "群体结构、信念机制、消息冲击、初始判断"],
            ["五 未关闭市场的预先结论", "未关闭市场预演", "未关闭",
             "SpaceX 相关市场;n=20;三种子"],
        ],
        widths_cm=[3.6, 2.8, 1.8, 4.3])
    para(doc,
        "研究问题一对应的复现实验把每个市场的真实结算作为比较对象,但"
        "比较并不只看“最后是否猜对”。本文同时考察两个指标:一是仿真"
        "终态价格是否落在真实结果对应的一侧;二是仿真过程中价格是否朝"
        "真实结果方向移动。前者容易受到市场起始价格本身的影响,后者"
        "更能反映智能体在仿真过程中是否产生了新的价格发现。")
    para(doc,
        "研究问题二对应的规模实验固定 Roman Roy 已关闭市场,分别设置 "
        "10、20、50 个智能体,每个规模使用三个随机种子。这样可以观察"
        "随着参与者数量增加,交易量、撤单比例、价格波动、资金流网络"
        "和个体损益分布是否发生系统性变化。如果规模扩大只增加动作"
        "数量而不改变价格和网络结构,说明工具在该市场上主要复现了"
        "局部交易行为;如果规模扩大使资金流更集中或价格路径更稳定,"
        "则说明智能体群体可能出现了新的聚合现象。")
    para(doc,
        "研究问题三对应的时长实验固定同一市场、固定 20 个智能体与"
        "其余全部参数,只把决策轮数分别设为 10、20、40 轮,每个轮数"
        "使用三个随机种子。它用于把模拟时长这一个变量单独隔离出来:"
        "若价格随轮数持续漂移,说明结论依赖于何时停止仿真;若价格在"
        "若干轮后趋于稳定,说明结论对时长不敏感、工具具有内在的收敛"
        "性质。")
    para(doc,
        "研究问题四对应的消融实验用于判断工具内部设计的作用。本文"
        "分别比较行为原型群体与随机群体、显式信念机制开与关、注入"
        "消息与无消息、以及初始主观判断修正前与修正后,服务于一个"
        "直接问题:哪些设计改变了智能体模拟出的交易者行为,哪些设计"
        "改变了市场层面的结果。")
    para(doc,
        "研究问题五对应的未关闭市场预演实验不使用真实结算评分。它的"
        "输出包括:仿真前后 YES 价格区间、智能体信念分布、净买入或"
        "净卖出压力、交易活跃度、撤单和观望比例,以及主要分歧来源。"
        "这样的结论不是“预测一定正确”,而是在结算前把智能体群体如何"
        "理解市场、如何交易、分歧在哪里整理出来。")
    three_line_table(doc, "仿真结果与真实市场的比较指标",
        ["比较对象", "指标", "解释"],
        [
            ["仿真价格与真实结算", "终态是否在正确一侧;是否向真值移动", "区分价格起点本来含信息,还是 Agent 交易带来价格发现"],
            ["Agent 行为结构", "限价单、市价单、撤单、不操作、信念声明占比", "判断 Agent 是稳定交易,还是反复挂撤或观望"],
            ["Agent 间交互", "总资金流;资金流网络熵", "观察消息是否改变交易关系,或只是放大已有交易量"],
            ["个体结果", "结算后 P&L 分布", "观察不同原型内部是否有收益分化"],
            ["未关闭市场预演", "价格区间;群体信念;净交易压力", "在无结算标签时给出可提前阅读的判断"],
        ],
        widths_cm=[3.2, 5.0, 6.0])
    para(doc,
        "实验流程为:由真实数据导出市场参数与参与者画像;在只用事件前数据的前提下"
        "构造群体;以确定性方式初始化撮合环境的初始流动性;组织智能体"
        "进行固定轮数的多轮交易;事件结算后核算个体损益;对每一仿真"
        "完整记录其动作序列、成交、持仓与盘口轨迹以供分析与复现。")

    # ---------- 第六章 实验结果 ----------
    pagebreak(doc)
    h1(doc, "第六章  实验结果")

    para(doc,
        "本章按第二章的五个研究问题逐节给出实验结果。在进入各问题之前,"
        "先确立一条比较基线:在配置完全固定、决策温度为零时,仅随机"
        "种子变化就使仿真终态的 YES 中间价呈 0.222 ± 0.045 的波动。"
        "这表明语言模型后端在零温度下仍非完全确定,随机性经由群体"
        "抽样与轮内处理顺序进入。0.045 因此构成本研究一切组间比较的"
        "可检出下限:任何小于该量级的差异都不能与随机噪声区分。三个"
        "随机种子下的价格轨迹如下图所示。")
    figure(doc, "fig2_seed.png", "仅随机种子变化时的价格轨迹(随机性基线)")

    h2(doc, "一、智能体能否模拟出真实交易者的行为")
    para(doc,
        "研究问题一在十个已关闭、覆盖体育、加密货币、政治等多种类型的"
        "市场上检验复现效果。比较分两层:终态价格是否落在真实结果对应"
        "的一侧,以及仿真过程中价格是否朝真实结果方向移动。十个市场中,"
        "仿真终价落在正确一侧者为七个,但二项检验不显著(p ≈ 0.17),"
        "且这一表面正确率几乎完全来自市场开始时的初始价格本身已含信息,"
        "而非智能体在交易中产生的价格发现;真正衡量价格发现的指标"
        "——价格朝真实方向移动者——仅为三个,显著差于随机猜测。"
        "十个市场仿真期内价格相对起点的归一化轨迹见下图。")
    figure(doc, "fig10_b1_normalized.png",
           "十市场仿真期内价格相对起点的归一化轨迹(每条线对应一个市场)",
           width_cm=13)
    three_line_table(doc, "十市场跨市场诊断明细(真实结果:1=是,0=否)",
        ["市场", "真实结果", "起始价格", "终态价格", "向真值移动", "终态正确侧"],
        [
            ['狗狗币>0.34', 1, 0.950, 0.905, '否', '是'],
            ['NBA POR-MIA', 1, 0.215, 0.240, '是', '否'],
            ['乌拉圭大选', 1, 0.500, 0.735, '是', '是'],
            ['NBA GSW-MIN', 1, 0.330, 0.355, '是', '否'],
            ['德国组阁', 1, 0.950, 0.880, '否', '是'],
            ['XRP<1.50', 0, 0.055, 0.080, '否', '是'],
            ['NBA PHX-IND', 0, 0.475, 0.540, '否', '否'],
            ['BTC<78000', 0, 0.055, 0.130, '否', '是'],
            ['XRP<1.00', 0, 0.060, 0.160, '否', '是'],
            ['马斯克买MSNBC', 0, 0.055, 0.055, '否', '是'],
        ],
        widths_cm=[3.0, 1.8, 2.0, 2.0, 2.2, 2.2])
    figure(doc, "fig6_external.png",
           "十个市场仿真过程中价格的移动方向(深色=朝真实结果移动)",
           width_cm=12)
    para(doc,
        "从交易者行为本身看,智能体复现出的微观结构是合理的:在基底"
        "市场上,动作以挂出限价单为主,辅以少量按盘口立即成交,撤单"
        "占比稳定在一成多;成交、持仓与损益均能被撮合环境完整记录与"
        "统计。也就是说,智能体能模拟出一个结构上可信的交易者群体与"
        "可运转的市场过程。但价格层面存在一个一致的方向性偏差:仿真"
        "价格系统性地偏离真实结果方向。这一偏差并非智能体推理能力的"
        "固有局限,而是一处可定位、可修正的方法缺陷,其诊断与修正在"
        "本章第四节给出。综合而言,对研究问题一的回答是:智能体能"
        "复现可信的交易者行为与市场微观结构,但在初始价格已含信息的"
        "市场上,不会自行把价格推向真实结果。")

    h2(doc, "二、智能体数量如何影响行为模拟")
    para(doc,
        "研究问题二固定 Roman Roy 已关闭市场(真实结果为否),把智能体"
        "数量设为 10、20、50,每个规模三个种子。结果显示:仿真终价"
        "在三个规模下分别为 0.165、0.190、0.167(均值),彼此之差以及"
        "与规模的关系都落在随机性基线之内,不随规模系统性变化;价格"
        "也始终停留在初始价附近,没有因为参与者增多而更接近真实结果。"
        "与此同时,交易活跃度随规模近似成比例增长:成交笔数由约 22 "
        "笔增至约 80 笔再到约 230 笔,成交名义额由约一千美元增至约"
        "两万五千美元。撤单占比在三个规模下稳定在 7% 至 8%。各规模"
        "的核心指标见下图与下表。")
    figure(doc, "fig13_scale.png",
           "智能体数量对终态价格、交易量与价格波动的影响"
           "(误差棒为种子标准差)", width_cm=15)
    three_line_table(doc, "规模实验各规模核心指标(三种子聚合)",
        ["智能体数", "终态价格(均值±标准差)", "价格波动",
         "成交名义额", "成交笔数", "撤单占比%"],
        _load_scale_rows(),
        widths_cm=[1.8, 4.0, 1.8, 2.4, 1.8, 1.8])
    para(doc,
        "对研究问题二的回答是:在该市场上,增加智能体数量主要带来"
        "成比例增长的流动性与交易活跃度,而不改变价格水平、不使价格"
        "更接近真实结果,也没有产生新的群体层面价格现象——市场的"
        "价格结构与撤单行为对规模近似不变。一个值得注意的副现象是,"
        "个体损益的离散程度随规模明显扩大:规模越大,既有更显著盈利"
        "的智能体,也有更显著亏损的智能体。这说明规模扩大放大的是"
        "个体之间的结果分化,而非市场整体的价格发现能力。")

    h2(doc, "三、模拟时长如何影响行为模拟")
    para(doc,
        "研究问题三固定同一市场与 20 个智能体,只把决策轮数设为 10、"
        "20、40 轮,每个轮数三个种子。结果显示:仿真终价在三种时长下"
        "分别为 0.190、0.167、0.180(均值),差异落在随机性基线之内,"
        "不随时长系统性变化。动作总量随轮数近似线性增长(约 216、"
        "436、833 次),说明更长的仿真主要是把同类交易行为重复更多轮。"
        "更关键的是逐轮价格波动:它在 10 轮时最高,到 20 轮、40 轮时"
        "下降并趋平,且在 40 轮的实验中,价格在后半段连续多轮几乎"
        "不动、成交也降到个位数。各时长的指标与价格路径见下图与下表。")
    figure(doc, "fig14_tick.png",
           "决策轮数对终态价格、动作总量与价格路径的影响"
           "(误差棒为种子标准差)", width_cm=15)
    three_line_table(doc, "时长实验各轮数核心指标(三种子聚合)",
        ["决策轮数", "终态价格(均值±标准差)", "价格波动",
         "动作总量", "成交笔数"],
        _load_tick_rows(),
        widths_cm=[2.0, 4.2, 2.0, 2.4, 2.0])
    para(doc,
        "对研究问题三的回答是:更长的模拟时长只增加成比例的交易活动,"
        "并不使价格持续漂移——价格在约 20 轮后趋于稳定,逐轮波动下降"
        "并趋平。这说明本工具具有内在的收敛性质:在该市场上,只要"
        "仿真运行到约 20 轮以上,结论对“何时停止仿真”并不敏感。需"
        "如实指出,终态价格的种子间标准差随时长略有扩大(由 10 轮的"
        "约 0.007 增至 40 轮的约 0.037),即更长的仿真在收敛之外也"
        "累积了更多种子相关的离散,这一点在解读长时仿真时应予考虑。")

    h2(doc, "四、哪些设计决定行为模拟的质量")
    para(doc,
        "研究问题四通过消融实验逐一改变工具的内部设计,判断哪些设计"
        "真正影响智能体模拟出的交易者行为。下图与下表先给出全部八组"
        "对照的动作类型分布:除“信念开”组将约四成动作用于显式声明"
        "信念外,其余七组的动作结构几乎不可分辨,提示信念机制是其中"
        "效应最强的处理。")
    figure(doc, "fig12_action_mix_groups.png",
           "八组实验的动作类型分布对比")
    three_line_table(doc, "八组实验的动作类型分布(占全部动作百分比)",
        ["实验组", "限价单", "市价单", "撤单", "不操作",
         "拆分", "合并", "声明信念"],
        _load_action_mix_rows(),
        widths_cm=[2.2, 1.5, 1.5, 1.4, 1.6, 1.4, 1.4, 1.8])
    para(doc,
        "(一)群体构造方式。在仿真终价上,行为原型群体为 0.243 ± "
        "0.044,均匀随机群体为 0.225 ± 0.056,二者之差仅约 0.018,"
        "落在随机性基线之内(Welch 检验 p ≈ 0.68);与边际匹配随机"
        "群体之差亦不显著。对聚类本身的独立再分析显示,聚类标签对"
        "未参与聚类的另一半数据上的特征分布,其预测增益虽统计显著"
        "但幅度仅约百分之三,且不传导至总体市场动态。结论是:行为"
        "原型相较朴素的随机抽样,在整体市场结果上不产生可检出差异,"
        "应被重新定位为对参与者总体的描述性分类。三种群体的终态"
        "价格对比见下图。")
    figure(doc, "fig3_population.png",
           "三种群体的终态价格对比(误差棒为种子标准差,散点为单次仿真)",
           width_cm=11)
    para(doc,
        "将行为原型群体的智能体按所属原型分层后,四类原型表现出量级"
        "相当、方向一致的盈亏轮廓:盈亏均值均为小幅正值,标准差远大"
        "于均值,每类内部都同时存在显著盈利与显著亏损的个体。原型在"
        "群体行为分化上是可识别的,但这种分化未传导到市场总体动力学。")
    three_line_table(doc,
        "行为原型群体内,各原型智能体的盈亏分布(三种子合并)",
        ["原型", "智能体数", "盈亏均值", "盈亏标准差",
         "盈亏中位", "盈亏最小", "盈亏最大"],
        _load_archetype_pnl_rows(),
        widths_cm=[2.6, 1.8, 2.2, 2.4, 2.0, 2.0, 2.0])
    para(doc,
        "(二)显式信念机制。引入显式信念机制后,无意义地反复挂单又"
        "撤单的占比由 12.4% 降至 7.1%(按种子配对检验,差异约 5.3 个"
        "百分点,p ≈ 0.028,显著);不做任何操作的占比由 16.9% 降至 "
        "3.3%;智能体将约 45% 的动作用于显式陈述对结果的后验信念。"
        "这是四组消融中唯一具有显著且可解释效应的处理,说明无意义"
        "挂撤这一行为噪声主要源于“缺乏对自身信念的可见性”这一建模"
        "选择,而非语言模型推理能力的固有缺陷。信念机制开关下的动作"
        "结构与个体盈亏分布见下两图。")
    figure(doc, "fig4_belief.png",
           "信念机制开关下的动作结构对比", width_cm=12)
    figure(doc, "fig11_b4_pnl_kde.png",
           "信念机制开关下,个体智能体盈亏分布的对比(每组三种子合并)",
           width_cm=12)
    para(doc,
        "(三)外部消息冲击。中途注入的传闻使仿真终价仅变动约 0.010,"
        "落在随机性基线之内;参与者间资金流动网络的连接集中—分散"
        "程度(以信息熵衡量)几乎不变(由 3.37 降至 3.33),但网络"
        "总资金流增加约 26%。这提示冲击的传导形态是“在既有流动路径"
        "上放大交易量”,而非“重构网络拓扑”。受限于每组三次重复,此"
        "为初步结果。资金流与网络拓扑对比见下两图。")
    figure(doc, "fig5_shock.png",
           "信息冲击下的资金流与网络结构对比", width_cm=13)
    figure(doc, "fig9_network_b6.png",
           "无冲击与注入传闻下的资金流动网络拓扑", width_cm=14)
    para(doc,
        "(四)初始主观判断的生成方式。这是研究问题一中价格方向性"
        "偏差的根源。下文定位并修正这一方法缺陷。")
    para(doc,
        "如本章第一节所述,四组对照与十市场面板均显示出一个一致现象:"
        "仿真过程中价格系统性地偏离真实结果方向,真正衡量价格发现的"
        "指标——价格朝真实方向移动者——仅为十分之三,显著差于随机。"
        "对该现象的机制分析定位到初始主观判断的生成方式。当共识先验"
        "接近 0(即市场较确信结果为否)时,以“取值落在允许范围外就丢弃、重新抽取”的方式生成的"
        "先验,其被截断的左尾使实际期望被抬高至预期的两倍以上;智能体"
        "据此理性地判断“结果合约被低估”而一致地买入同一侧,推动价格持续偏离"
        "真实方向。改用原生有界、精确保持目标期望的分布后,先验的实际"
        "期望与目标一致(偏差不超过 0.01),该偏差消除。")
    para(doc,
        "一组前后对照确认了上述诊断:在其余条件完全相同、仅替换先验"
        "生成方式时,价格相对市场开始时初始价格的平均偏移由 +0.067"
        "(系统性偏离真实方向)降至 +0.005(基本持平),终态价格由 0.222 ± 0.045 "
        "降至 0.160 ± 0.035。系统性朝同一方向的系统性偏离被消除约一个数量级。需"
        "如实指出:终值之差(0.062)虽大于随机性基线,但在三次重复下"
        "尚未达到常规统计显著(p ≈ 0.14),故应理解为“差异幅度可观、"
        "方向一致、尚待以更多重复正式确证”。还需强调:偏差被移除后,"
        "价格仅停留在本就含信息的、市场开始时的初始价格附近,并未主动收敛至真值,"
        "框架并不因此具备方向预测能力。这一发现的意义在于:此前观察"
        "到的方向性失败,有相当部分并非框架不可逾越的局限,而是一处"
        "可定位、可修正的方法缺陷;但修正它并不改变“框架是行为动力学"
        "研究仪器而非预测器”这一基本界定。修正前后的价格偏移对比见"
        "下图,关键指标见下表。")
    figure(doc, "fig7_fix.png",
           "修正前后价格偏移对比(误差棒为种子标准差)", width_cm=10)
    three_line_table(doc, "初始判断生成方式修正前后对比",
        ["指标", "修正前", "修正后"],
        [
            ["终态价格(均值±标准差)", "0.222 ± 0.045", "0.160 ± 0.035"],
            ["相对起始价的平均偏移", "+0.067", "+0.005"],
            ["向真值移动的仿真数", "0 / 3", "1 / 3"],
            ["撤单占比", "约 12%", "约 15%"],
        ],
        widths_cm=[5.4, 4.0, 4.0])
    para(doc,
        "对研究问题四的回答是:四项设计中,显式信念机制是唯一对交易者"
        "行为有显著且可解释影响的设计——它大幅减少无意义挂撤与空转;"
        "初始主观判断的生成方式则决定了价格是否系统性偏离真实方向,"
        "是一处影响结果有效性的关键设计;群体构造的粒度与外部消息"
        "冲击在现有重复次数下均未对市场层面结果产生可检出影响。")

    h2(doc, "五、未关闭市场的预先结论")
    para(doc,
        "研究问题五在尚未关闭的 SpaceX 相关市场上做预演,设 20 个"
        "智能体、三个种子。由于市场尚无真实结算,本节不报告命中率与"
        "结算损益,只考察智能体模拟出的交易者行为能否汇聚成一个"
        "可阅读、且多次模拟之间一致的预先判断。三个种子下,YES 价格"
        "都从市场开始时的约 0.665 起步,温和上行至 0.675 至 0.695 "
        "之间,漂移幅度在 +0.010 至 +0.030 之间;三个种子的终态价格"
        "散布不超过 0.02,落在随机性基线之内。三条价格路径见下图,"
        "各种子指标见下表。")
    figure(doc, "fig15_open.png",
           "未关闭市场预演的三条价格路径(SpaceX 相关市场,三种子)",
           width_cm=12)
    three_line_table(doc, "未关闭市场预演各种子指标",
        ["种子", "起始价格", "终态价格", "价格漂移", "价格波动", "成交笔数"],
        _load_open_rows(),
        widths_cm=[2.0, 2.2, 2.2, 2.2, 2.2, 2.0])
    para(doc,
        "对研究问题五的回答是:在未关闭市场上,智能体模拟出的交易者"
        "行为能够汇聚成一个有意义的预先判断——此处为“维持在约 68% "
        "的 YES 概率、并带温和上行倾向”;且这一判断在三个独立种子"
        "之间稳定一致。需强调,这是结算前的情景证据,用于在结算前"
        "组织信息、暴露分歧,而非已被验证的预测准确率;其正确与否"
        "须待市场真实关闭后方能评判。")

    # ---------- 第七章 实验结论 ----------
    pagebreak(doc)
    h1(doc, "第七章  实验结论")
    para(doc,
        "本研究面向 Polymarket 预测市场,建立了一个由大语言模型驱动的"
        "多智能体仿真工具,并用它检验智能体能否模拟真实交易者的行为。"
        "下面依次回答第二章提出的五个研究问题,再明示工具的适用边界。")
    h2(doc, "一、智能体能否模拟出真实交易者的行为")
    para(doc,
        "在覆盖体育、加密货币、政治等多种类型的十个已关闭市场上,智能体"
        "复现出的交易者行为在结构上是可信的:动作以挂出限价单为主,辅以"
        "少量即时成交与一成多的撤单,成交、持仓与损益均可被撮合环境完整"
        "记录。也就是说,工具能模拟出一个结构合理的交易者群体与可运转的"
        "市场过程。但在价格层面,真正衡量价格发现的指标——价格朝真实"
        "结果方向移动——仅为十分之三:在初始价格已含较强信息的市场上,"
        "智能体不会自行把价格推向真实结果。结论是:智能体能模拟可信的"
        "交易者行为与市场微观结构,但不具备端到端的方向预测能力。")
    h2(doc, "二、智能体数量如何影响行为模拟")
    para(doc,
        "在固定市场上把智能体数量由 10 增至 20、再到 50,仿真终态价格"
        "始终停留在初始价附近、不随规模系统性变化,也未更接近真实结果;"
        "交易量与成交笔数则随规模近似成比例增长,撤单占比稳定在 7% 至 "
        "8%。增加智能体主要带来成比例的流动性,而非新的群体层面价格"
        "现象——市场的价格结构对规模近似不变。规模扩大放大的是个体"
        "之间的损益分化,而非市场整体的价格发现能力。")
    h2(doc, "三、模拟时长如何影响行为模拟")
    para(doc,
        "在固定智能体数量、只改变决策轮数(10、20、40 轮)时,动作总量"
        "随轮数近似线性增长,但仿真终态价格不随时长系统性变化,逐轮"
        "价格波动在约 20 轮后下降并趋平。这说明工具具有内在的收敛性质:"
        "只要仿真运行到约 20 轮以上,结论对“何时停止仿真”并不敏感。"
        "需指出,终态价格的种子间离散随时长略有扩大,解读长时仿真时"
        "应予考虑。")
    h2(doc, "四、哪些设计决定行为模拟的质量")
    para(doc,
        "四项消融中,显式信念机制是唯一对交易者行为有显著且可解释影响"
        "的设计:为智能体引入一个可在各轮之间持久保留的信念状态,能"
        "显著消解无意义地反复挂单又撤单这一行为噪声,说明该噪声主要"
        "源于建模方式的选择,而非语言模型本身的推理缺陷。初始主观判断"
        "的生成方式则决定结果是否有效:若采用“超出取值范围就丢弃重取”"
        "的抽样办法,会在市场较确信时系统性抬高其平均值,诱导群体一致"
        "偏离真实方向;改用取值天然有界、精确保持目标平均值的分布后,"
        "价格相对开始时的平均偏移由 +0.067 降至 +0.005。群体构造的"
        "粒度与外部消息冲击在现有重复次数下均未对市场层面结果产生"
        "可检出影响——其中消息冲击以“在既有资金流动路径上放大交易量”"
        "而非“重构网络拓扑”的形态传导。")
    h2(doc, "五、未关闭市场能否给出预先结论")
    para(doc,
        "在尚未关闭的 SpaceX 相关市场上,智能体模拟出的交易者行为能"
        "汇聚成一个有意义且可阅读的预先判断——此处为“维持在约 68% 的"
        " YES 概率、并带温和上行倾向”——且这一判断在三个独立种子之间"
        "稳定一致。这表明工具能在结算前组织信息、暴露分歧并给出可观察"
        "的情景判断;但它是结算前的情景证据,而非已被验证的预测准确率。")
    h2(doc, "六、适用范围与未来工作")
    para(doc,
        "综合五个问题,本工具的适用范围需被明确:在初始价格已含较强"
        "信息时,工具的价值在于刻画交易者行为与市场微观结构的过程,"
        "而非对最终结算方向做端到端的预测。该界定并不削弱前述结论,"
        "因为前述结论衡量的是行为结构、规模与时长的影响、信息传导与"
        "方法学健壮性,而非价格预测精度。")
    para(doc,
        "未来工作包括三个方向:在修正后的初始判断设定下系统重做"
        "受控对照与跨市场面板,以量化方向性偏离被消解的程度并提升其"
        "统计显著性;以更多随机种子重复确认规模、时长与信息冲击的"
        "效应;以及在更广的市场类型与更大的群体规模上检验上述结论的"
        "稳健性,并进一步把该工具扩展到日内更高频的微观市场场景。")

    # ---------- 参考文献 ----------
    pagebreak(doc)
    h1(doc, "参考文献")
    for r in REFERENCES:
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing = 1.5
        pf.left_indent = IND_HANG          # 悬挂缩进
        pf.first_line_indent = -IND_HANG
        run = p.add_run(r)
        _set_run(run, ea=SONG, size=PT_BODY)

    # ---------- 致谢 ----------
    pagebreak(doc)
    h1(doc, "致  谢")
    para(doc,
        "感谢导师在选题、方法与写作上的悉心指导;感谢提供公开数据与"
        "文档的开源社区;感谢同窗的讨论与建议。文中所有结论与不足"
        "由作者负责。")

    # ---------- 附录 ----------
    pagebreak(doc)
    h1(doc, "附录 A  行为原型的数据画像")
    para(doc,
        "本附录给出在只使用事件发生前数据的前提下,经标准化特征重新聚类得到的"
        "四类行为原型的数据画像。需再次强调,正文第六章已证其为描述性"
        "分类,在整体市场结果上不起决定性作用,此处仅供刻画参与者总体的"
        "异质性结构之用。", )
    para(doc,
        "四类原型在七个行为特征上的轮廓先以下图展示,具体中心坐标见"
        "随后表格。特征均以标准化前的原始量纲呈现;占比为该原型在事件前"
        "参与者池中的人数比例。雷达图中,各特征经跨原型 min-max 归一化"
        "以便在同一坐标下并置比较。")
    figure(doc, "fig8_archetype_radar.png",
           "四类行为原型在七个行为特征上的中心轮廓(各特征经跨原型归一化)",
           width_cm=12)
    three_line_table(doc, "四类行为原型的中心特征(基底市场,事件前参与者池)",
        ["原型", "占比", "累计名义额", "市场集中度",
         "单位资金市场广度", "平均成交价", "尾部交易占比", "成交价波动"],
        [
            ["原型一", "27.7%", "2.61", "0.39", "6.31", "0.51", "0.22", "0.24"],
            ["原型二", "35.2%", "2.50", "0.88", "0.98", "0.50", "0.02", "0.10"],
            ["原型三", "9.7%",  "2.84", "0.62", "1.45", "0.89", "0.70", "0.10"],
            ["原型四", "27.4%", "2.21", "0.84", "1.44", "0.35", "0.48", "0.24"],
        ],
        widths_cm=[1.6, 1.5, 2.0, 2.0, 2.6, 2.0, 2.0, 2.0])
    para(doc,
        "可见原型一对应“单位资金覆盖市场最广”的高活跃分散型参与者,"
        "原型二为“高度集中于单一市场、活跃时长极短”的一次性参与者,"
        "原型三为“平均成交价偏高、尾部极端价格交易多”的追逐小概率"
        "高赔率型,原型四为“成交价偏低、波动较大”的逆向型。再次强调,"
        "该分类为描述性,正文第六章已证其在整体市场结果上不起决定性作用。")

    h1(doc, "附录 B  实验复现说明")
    para(doc,
        "本文所有量化结论均可由随附的实验配置与分析制品复现:每一仿真"
        "完整记录其动作序列、成交、持仓与盘口轨迹;受控对照的设计、"
        "随机种子与导出参数均被固定记录。决策温度为零,语言模型后端"
        "为唯一的外部随机来源,其残余非确定性已在随机性基线中量化"
        "(终价 ±0.045),本文所有显著性判定均在该噪声带之上做出。")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    default_out = (Path.home() / "Desktop" /
                   "大语言模型驱动智能体的行为模拟研究——以Polymarket预测市场为例.docx")
    ap.add_argument("--out", default=str(default_out))
    ap.add_argument(
        "--template",
        default="/Users/moonshot/Projects/Poly/参考/附件1：2026届本科毕业论文工作手册/"
                "17-南京大学本科毕业论文模板【WORD版本】2026届更新.docx",
        help="NJU template .docx; falls back to a blank document if absent",
    )
    args = ap.parse_args()

    tpl = Path(args.template)
    if tpl.exists():
        doc = Document(str(tpl))
        # clear the template's placeholder body, keep its styles
        for p in list(doc.paragraphs):
            p._element.getparent().remove(p._element)
        for t in list(doc.tables):
            t._element.getparent().remove(t._element)
    else:
        doc = Document()

    _page_setup(doc)
    build(doc)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    print(f"wrote {out}  ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
