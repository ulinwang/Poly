# v15 行为模式目录

模式数 K = 4（在 rq1_panel 上拟合）。每个簇展示：top-5 |z| 特征 + 3 个最贴近中心的代表性 agent 的 reasoning 摘录。

## K 选择诊断

| K | silhouette | bootstrap Jaccard 中位 | 最小簇占比 | 有效 |
|---:|---:|---:|---:|---:|
| 3 | 0.109 | 0.744 | 0.240 | 是 |
| 4 | 0.112 | 0.643 | 0.150 | 是 |
| 5 | 0.105 | 0.479 | 0.110 | 是 |
| 6 | 0.106 | 0.522 | 0.090 | 是 |

## 模式 1：激进套利型

**特征指纹（top-5 |z|）**：

| 特征 | 中心 z 值 |
|---|---:|
| 现金投入斜率 | +1.52 |
| 归一收益 | +1.40 |
| 终态敞口比 | +1.36 |
| 下单规模均值占比 | +1.34 |
| 下单规模峰值占比 | +1.33 |

**代表性 agent reasoning 摘录**：

- agent=9 (sim 551ed60b…)：My prior was extremely high on this relationship rumor — it's the kind of weird celebrity-political gossip that could genuinely go viral. But the market mid is only 0.325, which suggests the crowd is deeply skeptical. I'm anchoring on my prior, but I acknowledge the market's price-discovery mechanis The crowd's mid at 0.325 is way below my 0.99 prior — this …
- agent=6 (sim 5f1cb209…)：My prior sits at 0.71, and the market mid (0.725) is pretty close — no new info to shift me. The order book is balanced and this is opening night, so I'll hold at my prior with moderate confidence. The market mid is 0.725, my prior is 0.71, so we're very close. The book is perfectly balanced with no order imbalance, and there's no history to read momentum fr…
- agent=13 (sim 15a3ba99…)：My prior stays at 0.93. Tesla's track record of overpromising FSD timelines is terrible, but the June 2026 window is generous. Elon's repeated 'next year' claims plus the recent unsupervised FSD demos suggest they'll make a credible push. Still, 1σ=0.37 reflects huge uncertainty — this is a moonshot My prior (0.93) is far above the market mid (0.64), so I se…

建议中文名：**激进套利型**（可在 `pattern_meta_v1.json` 中调整）

## 模式 2：信念锚定型

**特征指纹（top-5 |z|）**：

| 特征 | 中心 z 值 |
|---|---:|
| 限价单占比 | +0.80 |
| 撤单挂单比 | -0.74 |
| 语义维1 | -0.64 |
| 动作熵 | -0.62 |
| 语义维5 | +0.60 |

**代表性 agent reasoning 摘录**：

- agent=19 (sim 551ed60b…)：Starting prior was 0.38 with 1σ=0.10. The market mid is 0.325, slightly below my prior, suggesting a touch of skepticism. This is a celebrity romance rumor — low base rate for confirmed relationships, but non-zero given Trudeau's singleness and Perry's visibility. I'll anchor near my prior but shade My belief (0.35) sits above the mid (0.325). The 0.300 limi…
- agent=5 (sim 117eb7c7…)：My private prior of 63% reflects the structural pro-executive tilt of the current Supreme Court and the fact that IEEPA has historically been interpreted to grant the president broad emergency powers. However, the Federal Circuit ruled against the tariffs, and the Supreme Court's exact appetite for My prior of 63% is massively above the 26.5¢ market price fo…
- agent=4 (sim 551ed60b…)：Starting prior was 0.10 but the market mid is 0.325, so the crowd prices this much higher. However, there's no real evidence of a relationship—this is a meme speculation with almost zero confirmable basis. I'm anchoring on my prior but slightly tugged by the market; still very low conviction given t My belief says YES is worth ~0.08, market says 0.325 — huge…

建议中文名：**信念锚定型**（可在 `pattern_meta_v1.json` 中调整）

## 模式 3：频繁挂撤型

**特征指纹（top-5 |z|）**：

| 特征 | 中心 z 值 |
|---|---:|
| 撤单占比 | +0.72 |
| 撤单挂单比 | +0.68 |
| 语义维1 | +0.57 |
| 归一收益 | -0.55 |
| 现金投入斜率 | -0.53 |

**代表性 agent reasoning 摘录**：

- agent=8 (sim 59bef4c2…)：My prior from simulation start: deploying National Guard to D.C. by an arbitrary August deadline seems unlikely without a specific precipitating event. The tight bid-ask spread at 0.27/0.48 is still far above my prior, but I'll start with my prior and wait for more information. My prior is 0.14, so YES at 0.40+ is heavily overpriced. I'll place a sell limit …
- agent=12 (sim 15a3ba99…)：Prior of 0.69 based on Elon's history of overpromising FSD timelines, but Tesla's rapid iteration pace and the 18-month window (mid-2026) leave a non-trivial chance. The current mid of 0.64 is slightly below my prior, so I hold my belief above the market. My prior of 0.69 gives 5 ticks of edge vs the 0.640 mid. Splitting the current spread at 0.650 — I'm wil…
- agent=9 (sim 117eb7c7…)：Prior was 0.14 but the current YES mid at 0.265 suggests the market prices in a higher chance than I estimated. I'm updating slightly upward to 0.18, still well below the market's implied 0.265, because the Supreme Court tends to be deferential on national security (IEEPA) and Trump appointees domin My belief is 0.18 YES implying 0.82 fair for NO, but NO is …

建议中文名：**频繁挂撤型**（可在 `pattern_meta_v1.json` 中调整）

## 模式 4：信号反向型

**特征指纹（top-5 |z|）**：

| 特征 | 中心 z 值 |
|---|---:|
| 拆分合并占比 | +1.10 |
| 市价单占比 | +1.02 |
| 限价单占比 | -0.94 |
| 最大回撤 | -0.88 |
| 撤单占比 | -0.73 |

**代表性 agent reasoning 摘录**：

- agent=2 (sim 551ed60b…)：My prior that two unrelated high-profile figures will suddenly confirm a romantic relationship is very low. The market starting mid around 0.325 is higher than my prior, suggesting some speculative froth, but I'll hold near my prior until evidence emerges. Low confidence given this is a very uncerta My prior of 0.13 is far below the 0.325 mid, so I see value…
- agent=0 (sim 117eb7c7…)：My prior of 0.21 reflects skepticism that the Supreme Court will reverse the Federal Circuit's strong IEEPA ruling. The Court tends to uphold executive power on national security, but the Federal Circuit's decision was clear on statutory limits. Initial market price of 0.26-0.27 doesn't shift my vie My belief of 0.21 for YES implies NO is worth ~0.79, well a…
- agent=4 (sim 551ed60b…)：Starting prior was 0.10 but the market mid is 0.325, so the crowd prices this much higher. However, there's no real evidence of a relationship—this is a meme speculation with almost zero confirmable basis. I'm anchoring on my prior but slightly tugged by the market; still very low conviction given t My belief says YES is worth ~0.08, market says 0.325 — huge…

建议中文名：**信号反向型**（可在 `pattern_meta_v1.json` 中调整）
