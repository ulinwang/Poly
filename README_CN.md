# Poly

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*[English → README.md](README.md)*

## Poly 是什么？

Poly 是一个面向预测市场（如 Polymarket）的**多智能体仿真平台**。每个交易智能体由大语言模型驱动，在仿真的中央限价订单簿（CLOB）中交易，让研究者在可控、可复现的条件下研究价格形成、交易者行为涌现与市场动态。

核心特性：

* **LLM 智能体** —— 每个交易者有可配置的 persona、记忆和推理流程，并以真实链上钱包历史为先验。
* **多供应商（基于 litellm）** —— 一套接口覆盖 OpenAI、DeepSeek、Kimi(Moonshot)、xAI、Gemini、Mistral、Anthropic 以及任意 OpenAI 兼容端点；在「设置」页选择供应商/模型。
* **经验校准** —— 智能体先验与人群构成来自对真实 Polymarket 成交/持有数据的查询。
* **完整 CLOB 仿真** —— Gym 风格的订单簿环境，含 CTF 机制、手续费与结算。
* **Eval 评估层** —— 宏观（市场价格）与微观（每个 agent）指标实时流式推送到前端，并汇总为事后评分卡。
* **实时 Web 看板** —— React 19 单页应用：浏览市场 → 进入市场 → 运行实验 → 实时观察（SSE）。

## 架构

monorepo，Web 应用 / Python 仿真核心 / 离线研究流水线 清晰分层：

```text
Poly/                         (外层文件夹)
├── polymetl/                 ← git 仓库
│   ├── apps/
│   │   ├── web/              React 19 + Vite + Tailwind v4 前端
│   │   └── server/           TypeScript Fastify 后端（API + 托管 SPA）
│   ├── sim/                  Python 仿真核心
│   │   ├── agent/            persona、特征、prompt、决策(LLM)、记忆
│   │   ├── environment/      PolyEnv CLOB 引擎、订单簿、工具、seeder
│   │   ├── runner/           runner_cli.py + runner_stream.py（由后端 spawn）
│   │   └── evaluation/       指标 + eval 数据结构（宏观/微观）
│   ├── research/             离线分析（论文流水线）
│   │   ├── experiments/      批量运行、分析、作图
│   │   ├── comparison/  viz/  scripts/
│   ├── data/                 ETL + 查询层（ClickHouse 可选）—— 共享包
│   ├── legacy/               已废弃的旧 python webapp（保留参考）
│   ├── pyproject.toml        Python 依赖(uv)；多包根(sim, research, .)
│   └── package.json          npm workspaces (apps/web, apps/server)
└── thesis/                   论文成品（docx / ppt / 参考）—— 在仓库之外
```

运行时数据流：

```text
React SPA（开发 :5173，生产由 :8765 托管）
      │  REST /api/v1/*  +  SSE
      ▼
TS Fastify 后端（apps/server，:8765）
      │  spawn  .venv/bin/python3 sim/runner/runner_cli.py（JSON over stdin/stdout）
      ▼
Python 仿真核心（sim/runner → environment + agent → litellm）
      │  流式事件：tick_started、agent_decision、tick_finished、
      │  tick_metrics、agent_snapshots、settled …
      ▼
经 SSE 回传到实时观察页
```

* **前端** —— React 19、Vite 8、Tailwind CSS v4、Recharts、Zustand。
* **后端** —— TypeScript Fastify；better-sqlite3 存实验/设置；SSE 实时推送；托管打包后的 SPA。
* **仿真核心** —— Python；LLM 调用经 litellm 路由；API key 由后端注入（加密存储、绝不回传前端）。
* **数据** —— ClickHouse（可选，历史数据）+ SQLite（实验、设置）。

## 快速开始

### 前置

* Node.js 20+
* Python 3.11+ 与 [`uv`](https://github.com/astral-sh/uv)
* 至少一家 LLM 供应商的 API key（DeepSeek / OpenAI / Kimi / …）

### 运行

```bash
# 1. Python 依赖（创建 .venv，安装多包根 editable）
uv sync
uv pip install -e .

# 2. Node 依赖
cd apps/server && npm install
cd ../web && npm install
cd ../..

# 3. 配置
cp .env.example .env        # 填 LLM key；ClickHouse 可选

# 4a. 开发（热更新）：两个终端
cd apps/server && npm run dev      # API + 仿真，http://localhost:8765
cd apps/web    && npm run dev      # Vite 开发服务器 http://localhost:5173（/api 代理到 8765）
# 打开 http://localhost:5173

# 4b. 或生产方式（后端托管打包 SPA）
cd apps/web && npm run build
cd ../server && npm run dev        # 打开 http://localhost:8765
```

也可在「设置」页运行时切换供应商/模型/API key，无需重启。

> **端口** —— 开发前端 **5173**，后端/API + 生产 SPA **8765**。

## 配置

复制 `.env.example` 为 `.env`。LLM key 可写在这里，或在「设置」页填写（加密存储）。

| 变量 | 说明 |
|------|------|
| `POLYMETL_DEEPSEEK_API_KEY` / `_BASE_URL` / `_MODEL` | DeepSeek（默认） |
| `POLYMETL_KIMI_API_KEY` / `_BASE_URL` / `_MODEL` | Kimi (Moonshot) |
| `POLYMETL_OPENAI_API_KEY` | OpenAI |
| `POLY_SECRET` | 加密存储 API key 的主密钥（生产环境务必设置） |
| `POLY_ROOT` | spawn Python 仿真时使用的仓库根路径覆盖 |
| `POLYMETL_CLICKHOUSE_*` | ClickHouse 连接（可选） |

> 切勿提交 `.env`。

## 开发

### 测试

```bash
# 后端 (vitest)
cd apps/server && npm test && npm run lint

# 前端 (构建 + lint；hooks/stores 用 vitest)
cd apps/web && npm run build && npm run lint && npx vitest run
```

> `sim/` 下的 Python 包通过多包根 `pyproject` 配置保留历史顶层导入名
> （`import agent`、`environment`、`experiments`、`data`、`evaluation` …）。
> 移动 Python 文件后，重新执行 `uv pip install -e .` 刷新 editable 安装。

### REST API（`/api/v1`）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/markets` | GET | 列出实时市场（支持 `q`、`category`、`limit`、`offset`） |
| `/markets/:slug` | GET | 市场详情（按 slug 直查，含 `event_slug`） |
| `/experiments` | GET / POST | 列出 / 创建并启动实验 |
| `/experiments/:id` | GET | 实验详情 |
| `/experiments/:id/cancel` | POST | 取消运行 |
| `/experiments/:id/events` | GET | 实时仿真事件的 SSE 流 |
| `/settings/api` | GET / PUT | LLM 设置（key 不回传，返回 `api_key_set` 标志） |
| `/settings/test` | POST | 测试 LLM 连接 |
| `/providers` | GET | litellm 供应商/模型目录 |

## 许可

[MIT](LICENSE)。

## 致谢

* **Polymarket** —— 提供公开 API 与链上数据，支撑经验校准层。
* 本项目最初为一篇关于去中心化金融交易者行为的毕业论文而开发；论文与图表在本代码库之外（`../thesis/`）。

---

*Poly 是独立研究项目，与 Polymarket 无隶属或背书关系。*
