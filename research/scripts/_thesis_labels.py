"""Chinese chart labels for thesis v14 figures.

Action type codes (LIMIT, MARKET, …) and parameter symbols such as n, t
stay in English where they denote technical identifiers.
"""

from __future__ import annotations

MARKET_TITLE = {
    "robotaxi": "Robotaxi",
    "ethereum": "Ethereum",
}

PROFILE_VARIANT = {
    "natural": "自然",
    "uniform": "均匀",
    "concentrated": "集中",
}

THINKING_MODE = {
    "on": "开启",
    "off": "关闭",
}

# --- axis labels --------------------------------------------------------------
XLABEL_HORIZON_FRAC = "模拟进度"
XLABEL_DECISION_ROUND = "决策轮次"
XLABEL_N_AGENTS = "智能体数量 n"
XLABEL_PROFILE_MIX = "画像分布"
XLABEL_YES_MID = "YES 中间价"
XLABEL_YES_MID_SEED_AVG = "YES 中间价（种子均值）"
XLABEL_YES_MID_PATH = "YES 中间价（种子均值轨迹）"
XLABEL_YES_PROB = "YES 概率"
XLABEL_START_YES = "起始 YES 中间价"
XLABEL_END_YES = "终态 YES 中间价"
XLABEL_SEEDS_TOWARD_TRUTH = "朝真值移动的种子占比（%）"
XLABEL_ACTION_SHARE = "动作占比（%）"
XLABEL_CANCEL_SHARE = "撤单占比（%）"
XLABEL_AGENT_PNL = "智能体盈亏（USD）"
YLABEL_AGENT_PNL = XLABEL_AGENT_PNL
XLABEL_AGENTS = "智能体数"
XLABEL_FILL_NOTIONAL = "成交名义额（USD，对数刻度）"
XLABEL_FILLS = "成交笔数"
XLABEL_BELIEF_DECLARED = "声明 YES 概率"
XLABEL_CONFIDENCE = "声明置信度"
XLABEL_BELIEF_MINUS_PRICE = "信念 − 市场价格"
XLABEL_BELIEF_UPDATES = "每智能体 UPDATE_BELIEF 次数"
XLABEL_FIRST_TRADE_TICK = "首次成交轮次"
XLABEL_TRADE_CONSISTENCY = "与信念一致的交易占比"
XLABEL_N_SIMULATIONS = "仿真次数"
XLABEL_TRADE_COUNT = "交易笔数"
XLABEL_PREV_ACTION = "上一轮动作"
XLABEL_NEXT_ACTION = "下一轮动作"

YLABEL_END_MID = "终态 YES 中间价"
YLABEL_NOTIONAL = "成交名义额（USD）"
YLABEL_PNL_SPREAD = "盈亏极差（max − min）"
YLABEL_BELIEF_STD = "群体信念标准差"
YLABEL_AGENTS_SORTED = "智能体（按主导动作排序）"

# --- legends / annotations ----------------------------------------------------
LEGEND_TRUTH_YES = "真值 = YES"
LEGEND_TRUTH_NO = "真值 = NO"
LEGEND_TRUTH = "真值"
LEGEND_FINAL_PRICE = "终态价格"
LEGEND_MARKET_YES_MID = "市场 YES 中间价"
LEGEND_MEAN_BELIEF = "群体均值信念"
LEGEND_MARKET_OPEN = "开盘参考价"
LEGEND_NO_MOVEMENT = "无移动（y=x）"
LEGEND_OPEN_UNRESOLVED = "开放 / 未结算"
LEGEND_MEAN_SEEDS = "种子均值"
LEGEND_CHANCE = "随机基线 0.5"
LEGEND_START_PRICE = "起始价格"
LEGEND_TRUTH_MARKER = "真值"

CB_TRANSITION = "转移占比（行归一化，%）"
CB_ACTION_SHARE = "动作占比（%）"
CB_DECISION_ROUND = "决策轮次"


def market_title(key: str) -> str:
    name = MARKET_TITLE.get(key, key)
    return f"基底市场：{name}"


def suite_title(suite: str) -> str:
    return market_title(suite.replace("c5_", "").replace("c1_", ""))


def seed_label(i: int) -> str:
    return f"种子 {i}"


def rounds_label(t: int) -> str:
    return f"{t} 轮"


def n_label(n: int) -> str:
    return f"n={n}"


def t_label(t: int) -> str:
    return f"t={t}"


def thinking_label(mode: str) -> str:
    return f"思考 {THINKING_MODE.get(mode, mode)}"


def mean_label(value: float, digits: int = 2) -> str:
    return f"均值 = {value:.{digits}f}"


def median_label(value: float, digits: int = 0) -> str:
    return f"中位数 = {value:.{digits}f}"


def first_belief_label(n: int) -> str:
    return f"首次信念（n={n}）"


def last_belief_label(n: int) -> str:
    return f"末次信念（n={n}）"


def consistent_label(n: int) -> str:
    return f"一致（{n}）"


def inconsistent_label(n: int) -> str:
    return f"不一致（{n}）"


def end_price_truth_yes() -> str:
    return "终态（真值 YES）"


def end_price_truth_no() -> str:
    return "终态（真值 NO）"
