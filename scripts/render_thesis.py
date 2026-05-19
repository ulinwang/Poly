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
docs/v13/ and output_v13/ (see docs/v13/RESULTS_*.md).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def h1(doc, text):
    doc.add_heading(text, level=1)


def h2(doc, text):
    doc.add_heading(text, level=2)


def para(doc, text, indent=True):
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.first_line_indent = Cm(0.74)
    p.paragraph_format.line_spacing = 1.5
    p.add_run(text)
    return p


def bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.line_spacing = 1.5
    p.add_run(text)
    return p


def table(doc, headers, rows):
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    try:
        t.style = "Light Grid Accent 1"
    except KeyError:
        t.style = "Table Grid"
    for i, htext in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = htext
        for r in c.paragraphs:
            for rr in r.runs:
                rr.bold = True
    for ri, row in enumerate(rows, 1):
        for ci, v in enumerate(row):
            t.rows[ri].cells[ci].text = str(v)
    return t


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


def build(doc: Document) -> None:
    # ---------- 摘要 ----------
    h1(doc, "中文摘要")
    para(doc,
        "本研究探讨一个核心问题:由大语言模型驱动的多智能体群体,在预测市场"
        "这一信息聚合机制中,会复现出怎样的交易行为动力学,以及这种仿真在多大"
        "程度上可被当作研究真实市场参与者行为的可靠工具。本文以 Polymarket "
        "去中心化预测市场为研究对象,基于一百一十九万个真实钱包的链上交易历史"
        "构造行为画像,在一个连续竞价撮合环境中组织数十个语言模型智能体进行"
        "多轮交易,并围绕四个研究问题展开受控实验:随机性带来的不可约方差有"
        "多大;基于行为聚类的群体结构相较于随机群体是否在市场层面产生可检验"
        "的差异;为智能体引入显式且可持久的信念状态能否系统性改变其交易结构;"
        "以及一次外生信息冲击在群体中以何种形态传导。")
    para(doc,
        "研究得到三项可辩护的结论。第一,在只使用事件发生前数据的前提下,"
        "把参与者按行为特征聚类得到的群体,相较于只复现各特征总体分布、"
        "但打乱类别结构的随机群体,在市场层面不产生可检出的差异;聚类应"
        "被理解为对参与者总体的一种描述性刻画,而不是决定仿真结果的关键"
        "因素。第二,为智能体引入一个明确、可在各轮之间保留的信念状态,"
        "显著降低了无意义地反复挂单又撤单的行为,并使其决策结构发生实质"
        "改变,这表明此类行为噪声主要源于建模方式的选择,而非语言模型"
        "本身的能力缺陷。第三,本研究定位并修正了一处会使群体系统性偏离"
        "真实方向的方法缺陷:为智能体分配初始主观判断时,若采用“超出取值"
        "范围就丢弃重取”的抽样办法,会在群体看法本身较为确信时系统性地"
        "抬高其平均值,从而诱导群体一致地朝同一方向交易。修正后该偏差"
        "消除。本文据此明确界定:该仿真框架是研究交易行为规律的可控工具,"
        "而不是市场结果的预测器。")
    para(doc, "关键词:大语言模型;多智能体仿真;预测市场;行为金融;信息聚合", indent=False)

    pagebreak(doc)
    h1(doc, "Abstract")
    para(doc,
        "This thesis asks how a population of large-language-model agents "
        "behaves inside a prediction market — an information-aggregation "
        "mechanism — and to what extent such a simulation can serve as a "
        "reliable instrument for studying real market participants. Using "
        "the Polymarket decentralized prediction market, behavioral "
        "profiles are constructed from the on-chain trading history of "
        "1.19 million real wallets; dozens of language-model agents trade "
        "over multiple rounds in a continuous double-auction environment. "
        "Four controlled questions are studied: the irreducible variance "
        "from stochasticity; whether behavioral-cluster population "
        "structure produces a detectable market-level effect over a "
        "marginal-matched random population; whether an explicit, "
        "persistent belief state changes agents' trading structure; and "
        "how an exogenous information shock propagates.")
    para(doc,
        "Three defensible conclusions follow. First, under strict temporal "
        "cut-off, behavioral clustering yields no detectable market-level "
        "dynamics beyond a marginal-matched random population; clusters "
        "are descriptive, not causally load-bearing. Second, an explicit "
        "belief state markedly reduces meaningless order churn, indicating "
        "that this behavioral noise stems from a modeling choice rather "
        "than a model-capability deficit. Third, a methodological flaw is "
        "identified and corrected whereby boundary-truncated sampling of "
        "agents' private priors inflates their expectation on confident "
        "markets and induces one-sided trading. The framework is therefore "
        "delimited as a controlled instrument for studying trading "
        "behavioral dynamics, not a predictor of market outcomes.")
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
        "围绕“语言模型多智能体能否作为研究预测市场行为动力学的可靠工具”"
        "这一总问题,本文提出四个可证伪的子问题。")
    para(doc,
        "研究问题一(随机性基线):在决策温度为零、其余条件完全固定时,"
        "仅随机种子的变化会在仿真终态价格上引入多大的不可约方差?这一方差"
        "界定了后续一切处理效应能否被识别的下限,是所有比较的前提。")
    para(doc,
        "研究问题二(群体结构的因果作用):依据真实参与者的行为特征聚类"
        "得到的“行为原型”群体,相较于仅匹配总体边际分布的随机群体或完全"
        "均匀随机的群体,是否在市场层面产生可检出的动力学差异?换言之,"
        "聚类结构是仿真的起决定性作用的关键组成,还是仅为对参与者总体的描述性刻画?")
    para(doc,
        "研究问题三(信念机制的作用):若为智能体引入一个显式且可在轮次"
        "间持久保留的信念状态,而非令其每一轮从历史动作重新推断自身信念,"
        "能否系统性地降低无意义的反复挂单又撤单,并改变其决策结构?")
    para(doc,
        "研究问题四(外生冲击的传导形态):一次在仿真中途注入的信息冲击,"
        "是通过重构参与者之间的资金流动网络拓扑传导,还是仅在既有的流动"
        "路径上放大交易量?")
    para(doc,
        "需要预先声明:本研究不以“复现真实市场的结算方向”为目标,亦不"
        "宣称该框架具备方向预测能力。第七章将给出实证依据说明这一界定的"
        "必要性。框架的价值在于成为一个可控、可复现、可做受控对照的"
        "行为动力学研究仪器。")

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
        "尽量给出确定、可重复的回答,以最大化实验的可复现性。")

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
        "的不稳定被怀疑是无意义地反复挂单又撤单的来源之一;第七章给出检验。")

    h2(doc, "五、市场撮合环境")
    para(doc,
        "撮合环境实现一个标准的连续双向竞价订单簿,支持限价与市价委托、"
        "撤单、以及二元份额的拆分与合并,按价格-时间优先成交并阻止自成交。"
        "市场开始时的初始挂单由真实早期行情的价格、买卖价差与深度确定,"
        "交易费率与最小报价单位取自目标市场的真实参数。环境对智能体而言"
        "对智能体而言内部不可见,只能通过上述动作与之交互;智能体也无法看到其他智能体各自做了什么,"
        "以贴近真实市场的匿名性。")

    # ---------- 第四章 研究对象 ----------
    pagebreak(doc)
    h1(doc, "第四章  研究对象")
    para(doc,
        "研究对象为 Polymarket 去中心化预测市场及其真实参与者总体。"
        "Polymarket 以连续竞价订单簿撮合二元结果合约,事件结算后获胜"
        "结果合约价值归一、另一侧归零,为仿真提供了客观的结算标签。")
    para(doc,
        "参与者总体为一百一十九万个真实钱包的链上交易历史。其行为高度"
        "异质:既有极少数大额、跨市场分散的参与者,也有大量小额、集中于"
        "单一市场的参与者。本文以一个真实结算市场作为受控实验的基底,"
        "并辅以一个覆盖不同成交规模、不同结算方向的十市场面板,用于检验"
        "结论是否具有跨市场的外部效度。")
    para(doc,
        "在只使用事件发生前数据的前提下,基底市场可用的参与者群体经标准化特征重新聚类"
        "后稳健的类数为四,而非不做时间限制时表面上得到的五。这一差异并非"
        "细枝末节:它直接改变了用于刻画群体的原型,并在第七章的群体结构"
        "对照中产生实质后果。本文在附录中给出最终采用的四类行为原型的"
        "数据画像,并强调其为描述性分类。")

    # ---------- 第五章 实验过程 ----------
    pagebreak(doc)
    h1(doc, "第五章  实验过程")
    para(doc,
        "围绕四个研究问题设计四组受控对照,均以同一真实结算市场为基底,"
        "每组以三个不同随机种子重复,以便将处理效应与随机性区分开。")
    table(doc,
        ["实验", "操纵的变量", "对照方式", "回应的研究问题"],
        [
            ["随机性基线", "仅随机种子", "三次重复", "问题一"],
            ["群体结构", "行为原型 / 边际匹配随机 / 均匀随机",
             "三向对比,各三种子", "问题二"],
            ["信念机制", "显式信念机制 开 / 关", "配对,各三种子", "问题三"],
            ["信息冲击", "中途注入传闻 / 无冲击", "配对,各三种子", "问题四"],
        ])
    caption(doc, "表 5-1  四组受控对照实验设计")
    para(doc,
        "在四组对照之外,另以一个十市场面板检验外部效度:每个市场以相同"
        "的群体规模独立仿真,统计仿真终价落在正确一侧的比例,以及仿真"
        "过程中价格是否朝真实结果方向移动,并以二项检验判断是否优于随机。")
    para(doc,
        "实验流程为:由真实数据导出市场参数与参与者画像;在只用事件前数据的前提下"
        "构造群体;以确定性方式初始化撮合环境的初始流动性;组织智能体"
        "进行固定轮数的多轮交易;事件结算后核算个体损益;对每一仿真"
        "完整记录其动作序列、成交、持仓与盘口轨迹以供分析与复现。")

    # ---------- 第六章 实验细节 ----------
    pagebreak(doc)
    h1(doc, "第六章  实验细节")

    h2(doc, "一、随机性基线")
    para(doc,
        "在配置完全固定、决策温度为零时,仅随机种子变化即使仿真终态的"
        "YES 中间价呈 0.222 ± 0.045 的波动。这表明语言模型后端在零温度"
        "下仍非完全确定,随机性经由群体抽样与轮内处理顺序进入。0.045 "
        "因此构成本研究一切组间比较的可检出下限,亦是一项必须声明的"
        "可复现性限制:任何小于该量级的差异不能与随机噪声区分。")

    h2(doc, "二、群体结构的因果作用")
    para(doc,
        "在仿真终价上,行为原型群体为 0.243 ± 0.044,均匀随机群体为"
        "0.225 ± 0.056,二者之差仅约 0.018,落在随机性基线之内"
        "(Welch 检验 p ≈ 0.68);与边际匹配随机群体之差亦不显著。"
        "三种群体的撤单行为占比几乎一致(均在 14% 至 15% 之间)。")
    para(doc,
        "对聚类本身的独立再分析进一步支持这一结果:聚类标签对参与者"
        "另一半未参与聚类的数据上的特征分布的预测增益虽在统计上显著,但效应量仅约百分之三,"
        "且这一微弱增益不传导至总体市场动态。结论是一个稳健的负面发现:"
        "行为原型相较于朴素的随机抽样,在市场层面不产生可检出差异,"
        "应被重新定位为对参与者总体的一种描述性分类,而不是决定仿真结果的关键因素。"
        "其方法学含义是:在此类仿真中,群体异质性的恰当来源比聚类的"
        "粒度更值得关注。")

    h2(doc, "三、信念机制的作用")
    para(doc,
        "引入显式信念机制后,无意义地反复挂单又撤单的占比由 12.4% 降至 7.1%"
        "(按种子配对检验,差异约 5.3 个百分点,p ≈ 0.028,显著);"
        "不做任何操作的占比由 16.9% 降至 3.3%;智能体将约 45% 的动作用于显式"
        "陈述对结果的后验信念,而非反复挂单又撤单。这是四组对照中唯一具有"
        "显著且可解释效应的处理,说明无意义挂撤这一行为噪声主要源于"
        "“缺乏对自身信念的可见性”这一建模选择,而非语言模型推理能力"
        "的固有缺陷——仅赋予其显式、可持久的信念表征即可大幅消解。")

    h2(doc, "四、信息冲击的传导形态")
    para(doc,
        "中途注入的传闻使仿真终价仅变动约 0.010,落在随机性基线之内;"
        "参与者间资金流动网络的连接的集中—分散程度(以信息熵衡量,熵越大越分散)几乎不变(由 3.37 降至 3.33),"
        "但网络总资金流增加约 26%。这提示冲击的传导形态是“在既有流动"
        "路径上放大交易量”,而非“重构网络拓扑”。受限于每组三次重复,"
        "此为初步结果,其方向需以更多重复确认,列为后续工作。")

    h2(doc, "五、一处方法缺陷的定位与修正")
    para(doc,
        "四组对照与十市场面板均显示出一个一致现象:仿真过程中价格系统性"
        "地偏离真实结果方向。十市场面板中,仿真终价落在正确一侧者为"
        "十分之七,但二项检验不显著(p ≈ 0.17),且这一表面正确率几乎"
        "完全来自市场开始时的初始价格本身已含信息,而非智能体的价格发现;真正"
        "衡量价格发现的指标——价格朝真实方向移动者——仅为十分之三,"
        "显著差于随机。")
    para(doc,
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
        "尚未达到常规统计显著(p ≈ 0.14),故应理解为“效应量可观、"
        "方向一致、尚待以更多重复正式确证”。还需强调:偏差被移除后,"
        "价格仅停留在本就含信息的、市场开始时的初始价格附近,并未主动收敛至真值,"
        "框架并不因此具备方向预测能力。这一发现的意义在于:此前观察"
        "到的方向性失败,有相当部分并非框架不可逾越的局限,而是一处"
        "可定位、可修正的方法缺陷;但修正它并不改变“框架是行为动力学"
        "研究仪器而非预测器”这一基本界定。")

    # ---------- 第七章 实验结论 ----------
    pagebreak(doc)
    h1(doc, "第七章  实验结论")
    para(doc, "综合四组受控对照、十市场外部效度面板与机制分析,本文得到"
        "以下结论。")
    para(doc,
        "其一,把参与者按行为特征聚类得到的群体,在只用事件前数据的前提下,相较于仅复现"
        "各特征总体分布、但打乱类别结构的随机群体,在市场层面不起决定性作用。聚类只应作"
        "描述性使用,不应当作决定结果的机制。这是一个稳健、可辩护的负面结论,本身"
        "具有方法学价值。")
    para(doc,
        "其二,为智能体引入显式且可持久的信念状态,能显著消解无意义"
        "反复挂单又撤单这一行为噪声,并实质改变其决策结构。这说明该类噪声"
        "源于建模选择而非模型能力缺陷,对后续以语言模型构造市场参与者"
        "的工作具有可推广的方法启示。")
    para(doc,
        "其三,外生信息冲击以“放大既有流动路径上的交易量”而非“重构"
        "网络拓扑”的形态传导。此为初步结论,受样本量限制。")
    para(doc,
        "其四,也是对框架有效性边界最重要的界定:本文定位并修正了"
        "初始主观判断生成中的取值范围被截断所致的偏差。该偏差会在市场较确信时"
        "诱导群体系统性群体一致地朝同一方向交易,前后对照表明它正是此前“价格系统性"
        "偏离真实方向”现象的主要成因——修正后价格相对市场开始时"
        "初始价格的平均偏移由 +0.067 降至 +0.005,系统性朝同一方向的系统性偏离被消除约一个数量级"
        "(终值之差在三次重复下方向一致、效应量可观,但尚未达常规"
        "统计显著,需更多重复确证)。但需明确两点界定:其一,修正"
        "并不赋予框架方向预测能力,去偏后价格仅停留在本就含信息的、"
        "市场开始时的初始价格附近,而非主动收敛至真值;其二,框架的科学价值始终在于"
        "作为研究交易行为动力学的可控仪器,而非市场结果的预测工具。")
    para(doc,
        "未来工作包括:在修正后的先验设定下系统重做受控对照与外部"
        "效度面板,以量化方向性偏离被消解的程度;以更多重复确认信息"
        "冲击的传导形态;以及在更广的市场与更大的群体规模上检验上述"
        "结论的稳健性。")

    # ---------- 参考文献 ----------
    pagebreak(doc)
    h1(doc, "参考文献")
    for r in REFERENCES:
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = 1.5
        p.add_run(r).font.size = Pt(10.5)

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
        "分类,在市场层面不起决定性作用,此处仅供刻画参与者总体的"
        "异质性结构之用。", )
    para(doc,
        "(各原型在七个行为特征上的中心与分位数刻画,依据只含事件前数据的"
        "参与者池统计得到,具体数值见随附数据制品。)")

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

    build(doc)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    print(f"wrote {out}  ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
