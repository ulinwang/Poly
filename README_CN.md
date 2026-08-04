# Poly

[![CI](https://github.com/ulinwang/Poly/actions/workflows/ci.yml/badge.svg)](https://github.com/ulinwang/Poly/actions/workflows/ci.yml)
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
Poly/                         ← git 仓库
├── apps/
│   ├── web/                  React 19 + Vite + Tailwind v4 前端
│   └── server/               TypeScript Fastify 后端（API + 托管 SPA）
├── sim/                      Python 仿真核心
│   ├── agent/                persona、特征、prompt、决策（LLM）、记忆
│   ├── environment/          PolyEnv CLOB 引擎、订单簿、工具、seeder
│   ├── runner/               runner_cli.py + runner_stream.py（由后端 spawn）
│   └── evaluation/           指标 + eval 数据结构（宏观/微观）
├── research/                 离线分析（论文流水线）
│   ├── experiments/          批量运行、分析、作图
│   └── comparison/  viz/  scripts/
├── data/                     ETL + 查询层（ClickHouse 可选）—— 共享包
├── legacy/                   已废弃的旧 Python Web 应用（保留参考）
├── docker-compose.yml        前端、后端与 ClickHouse 服务
├── pyproject.toml            Python 依赖（uv）；多包根（sim、research、.）
└── package.json              npm workspaces（apps/web、apps/server）
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
# 1. 锁定的 Python 依赖（创建 .venv，安装多包根 editable）
#    若 uv 无法下载固定 Python，可使用已安装的 Python 3.11+：
#    uv sync --frozen --python python3
uv sync --frozen

# 2. Node 依赖（在 workspace 根目录安装）
npm install

# 3. 配置
cp .env.example .env        # 填 LLM key；ClickHouse 可选

# 4a. 开发（热更新）：两个终端
cd apps/server && npm run dev      # API + 仿真，http://localhost:8765
cd apps/web    && npm run dev      # Vite 开发服务器 http://localhost:5173（/api 代理到 8765）
# 打开 http://localhost:5173

# 4b. 或生产方式（后端托管打包后的 SPA）
npm run build:web
npm run build:server
cd apps/server && npm start        # 打开 http://localhost:8765
```

### 使用 Docker

```bash
# 先创建并配置环境变量
cp .env.example .env
# 编辑 .env，至少填写一个 LLM key

# 生成生产环境必需的密钥，并保存到 .env
export POLY_API_TOKEN="$(openssl rand -hex 32)"
export POLY_SECRET="$(openssl rand -hex 32)"
export POLYMETL_CLICKHOUSE_PASSWORD="$(openssl rand -hex 32)"
docker compose up --build --wait

# 前端及代理 API -> http://localhost:8080
# 就绪检查       -> http://localhost:8080/api/v1/health/ready
```

也可在「设置」页运行时切换供应商/模型/API key，无需重启。

生产 Compose 只发布 nginx 的 **8080** 端口。后端和 ClickHouse 位于私有
Compose 网络，`/api` 由 nginx 转发。后端以非 root 的 `node` 用户运行，
SQLite、checkpoint 和事件日志保存在 `backend-data` 命名卷中。

健康检查会按依赖顺序控制服务启动。Fastify 输出带请求 ID 的结构化 JSON
日志，并脱敏 Authorization、Cookie、API key 和 token。可用
`POLY_LOG_LEVEL` 调整日志级别。

完整的构建、启动、健康、非 root、网络隔离及清理冒烟测试：

```bash
./scripts/compose-smoke.sh
```

> **开发端口** —— Vite **5173**，Fastify **8765**；生产仅发布 nginx
> **8080**。

## 配置

复制 `.env.example` 为 `.env`。LLM key 可写在这里，或在「设置」页填写（加密存储）。

| 变量 | 说明 |
|------|------|
| `POLYMETL_DEEPSEEK_API_KEY` / `_BASE_URL` / `_MODEL` | DeepSeek（默认） |
| `POLYMETL_KIMI_API_KEY` / `_BASE_URL` / `_MODEL` | Kimi (Moonshot) |
| `POLYMETL_OPENAI_API_KEY` | OpenAI |
| `POLYMETL_LANGFUSE_PROMPT_MANAGEMENT_ENABLED` | 可选的托管提示词查询；本地 v1 始终兜底 |
| `POLYMETL_LANGFUSE_PUBLIC_KEY` / `_SECRET_KEY` / `_BASE_URL` | Langfuse Cloud 或自托管连接 |
| `POLYMETL_LANGFUSE_PROMPT_LABEL` / `_CACHE_TTL_SECONDS` | 托管提示词发布标签与 SDK 缓存 TTL |
| `POLYMETL_LANGFUSE_ENABLED` | 可选的 Langfuse Agent Loop 追踪，默认关闭 |
| `POLYMETL_LANGFUSE_ENVIRONMENT` / `_RELEASE` / `_SAMPLE_RATE` | 追踪环境、发布版本与采样率 |
| `POLYMETL_LANGFUSE_CAPTURE_POLICY` | `metadata`（安全默认）或 `full` 可见提示词/输出采集 |
| `POLY_SECRET` | 加密存储 API key 的主密钥（生产环境务必设置） |
| `POLY_ROOT` | spawn Python 仿真时使用的仓库根路径覆盖 |
| `POLY_API_TOKEN` | Operator Bearer Token；生产环境必填，至少 32 个字符 |
| `POLY_API_READ_TOKEN` | 可选的只读 API Bearer Token，至少 32 个字符 |
| `POLY_LOG_LEVEL` | 后端结构化日志级别（默认 `info`） |
| `POLY_MAX_EXPERIMENT_AGENTS` | 单次实验最大 Agent 数（默认 `100`） |
| `POLY_MAX_EXPERIMENT_TICKS` | 单次实验最大 Tick 数（默认 `200`） |
| `POLY_MAX_ACTIVE_RUNS` | 最大并发实验数（默认 `2`） |
| `POLY_EVENT_LOG_MAX_BYTES` | 单次实验事件日志上限（默认 `67108864`，64 MiB） |
| `POLY_EVENT_LOG_MAX_PENDING_BYTES` | 单次实验异步写入内存队列上限（默认 `4194304`，4 MiB） |
| `POLY_EVENT_LOG_RETENTION_DAYS` | 事件日志保留天数（默认 `30`） |
| `POLY_CHECKPOINT_MAX_BYTES` | 可恢复 checkpoint 大小上限（默认 `134217728`，128 MiB） |
| `POLY_CHECKPOINT_RETENTION_DAYS` | checkpoint 保留天数（默认 `30`） |
| `POLY_REPLAY_DEFAULT_LIMIT` | 单页回放事件默认数量（默认 `1000`） |
| `POLY_REPLAY_MAX_LIMIT` | 单页回放事件最大数量（默认 `5000`） |
| `POLY_LLM_ENDPOINT_ALLOWLIST` | 允许访问私网或 HTTP 自定义 LLM 端点的精确 origin（逗号分隔） |
| `POLYMETL_CLICKHOUSE_USER` | 本地/非 Compose 用户；Compose 固定为 `poly` |
| `POLYMETL_CLICKHOUSE_PASSWORD` | Compose 必填的非空 ClickHouse 密码 |
| `POLYMETL_CLICKHOUSE_DATABASE` | ClickHouse 数据库（默认 `polymetl`） |

### 可选 Langfuse LLMOps

系统提示词、状态提示词、belief 阶段和 trade 阶段现在都通过版本化 registry
解析。仓库内 v1 是默认值和强制兜底，因此提示词服务异常不会让 Agent tick
失败。每个 Decision 和 generation 生命周期事件都会记录来源、名称、版本/标签、
SHA-256 内容哈希、语言和渲染变量；公开 runner introspection 只暴露身份与变量名，
不暴露凭据和提示词正文。

安装提示词管理与可观测性支持：

```bash
uv sync --extra prompt-management --extra observability
```

按 `.env.example` 配置共用的 `POLYMETL_LANGFUSE_*` 连接参数。设置
`POLYMETL_LANGFUSE_PROMPT_MANAGEMENT_ENABLED=true` 可启用托管提示词。约定的
text prompt 名称为
`poly/clob-system/{en,zh}`、`poly/user-state/{en,zh}`、
`poly/belief-stage/{en,zh}` 和 `poly/trade-stage/{en,zh}`。选中的 Langfuse
prompt 对象会在同时启用追踪时直接关联到对应的 Langfuse generation。

发布和回退说明见 `sim/agent/prompt/README.md`。

设置 `POLYMETL_LANGFUSE_ENABLED=true` 后，每次实验会按
“experiment → tick → agent loop → generation/tool”记录。

追踪包含仿真/决策标识、persona 与预算、模型、耗时、token 用量、提示词占位
版本和错误。遥测始终 fail-open：SDK 或凭据缺失、导出服务故障、flush 超时
都不会改变实验行为。

推荐保留默认 `metadata` 策略，它不上传提示词、消息、工具参数、搜索结果和
模型输出内容。`full` 会在敏感字段脱敏后采集可见输入输出；模型隐藏推理和
原始响应永不导出。使用 Langfuse Cloud 前应先确认数据策略；自托管时把
`POLYMETL_LANGFUSE_BASE_URL` 改为自己的 HTTPS 地址。完整配置和生命周期
映射见 `sim/observability/README.md`。

自定义 LLM 端点默认必须使用 HTTPS，且只能解析到公网 IP。若需连接本地模型
服务等私网端点，请精确放行其 origin，例如
`POLY_LLM_ENDPOINT_ALLOWLIST=http://host.docker.internal:11434`。

> 切勿提交 `.env`。

事件日志使用有序异步 writer 落盘。存储失败或达到配置上限时，仿真会继续运行，
实验详情中的 `event_persistence` 会报告 degraded/limited 状态与丢弃事件数。
服务启动时会按上述保留天数清理过期 `.ndjson` 日志和 `.pkl` checkpoint。

默认部署不会发布 ClickHouse 端口。管理操作优先使用
`docker compose exec clickhouse clickhouse-client`。若确需外部访问，应使用
显式的本地 Compose override，并保留非默认用户名和密码。

### API 认证

生产模式在未配置 `POLY_API_TOKEN` 时会拒绝启动。可使用
`openssl rand -hex 32` 生成高熵 token。Web 界面会提示输入，token 仅保存在
当前标签页的 `sessionStorage` 中；API 与 SSE 请求通过
`Authorization: Bearer <token>` 发送，服务端不会接受 URL 查询参数中的凭据。

市场/事件浏览和静态供应商目录保持公开只读。设置、密钥、实验及历史/SSE、
供应商模型发现、Agent 内省和数据分析均需要认证。可选
`POLY_API_READ_TOKEN` 只能访问受保护的 GET/HEAD 路由，修改请求返回 HTTP 403。
Nginx 会原样转发 `Authorization` 请求头。

开发模式（在 `apps/server` 中运行 `npm run dev`）默认不启用认证；设置
`POLY_API_TOKEN` 即可在本地启用。直接调用 API：

```bash
curl -H "Authorization: Bearer $POLY_API_TOKEN" \
  http://localhost:8765/api/v1/experiments
```

## 开发

### 测试

```bash
# Python 仿真与研究回归套件（无需 API key / ClickHouse）
uv sync --frozen
uv run pytest -q

# sim/ 分支覆盖率；生成 coverage.xml，并执行 65% 门槛
uv run pytest -q --cov=sim --cov-report=term-missing --cov-report=xml

# 确定性 Agent Loop 数据集门禁（无需 LLM 或 Langfuse 凭据）
PYTHONPATH=sim:research:. uv run python -m evaluation.agent_loop.cli \
  tests/fixtures/agent_loop_eval.jsonl --fail-on-hard

# 后端 (vitest)
cd apps/server && npm test && npm run lint

# 前端 (构建 + lint；hooks/stores 用 vitest)
cd apps/web && npm run build && npm run lint && npx vitest run
```

### 持续集成

[GitHub Actions 工作流](.github/workflows/ci.yml)会在每个 Pull Request
以及每次推送到 `master` 时运行。Python 3.11 任务使用持久化 uv 缓存安装
`uv.lock` 的精确环境，运行 hermetic pytest 套件，并对 `sim/` 执行分支覆盖率
门槛。2026-07-29 测得的初始基线为 **66%**，回归门槛为 **65%**。供应商调用、
ClickHouse、Web 搜索和生成数据均被 mock 或跳过，因此 CI 无需 API key 或
实时网络。

Agent Loop 与 Multi-Agent 评估会先写入本地 `agent_scores` 和 `run_scores`
事件，并可选镜像到 Langfuse。评估器契约、离线 JSONL 格式和显式数据集同步
说明见 [`sim/evaluation/agent_loop/README.md`](sim/evaluation/agent_loop/README.md)。

Server 与 Web 任务使用 `npm ci` 安装锁定的 Node 依赖并缓存 npm 下载，然后在
Node.js 20 上执行后端 lint、测试、构建以及前端 lint、构建。三个任务独立运行，
便于快速定位失败环节。部署文件或后端源码变化时，按路径触发的
[Compose 冒烟工作流](.github/workflows/compose-smoke.yml)还会构建、启动、
健康检查并清理生产栈。

> `sim/` 下的 Python 包通过多包根 `pyproject` 配置保留历史顶层导入名
> （`import agent`、`environment`、`experiments`、`data`、`evaluation` …）。
> 移动 Python 文件后，重新执行 `uv pip install -e .` 刷新 editable 安装。

### REST API（`/api/v1`）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/markets` | GET | 列出实时市场（支持 `q`、不区分大小写的精确 `category`、`live_only`、`limit`、`offset`） |
| `/markets/:slug` | GET | 市场详情（按 slug 直查，含 `event_slug`） |
| `/experiments` | GET / POST | 列出 / 创建并启动实验 |
| `/experiments/:id` | GET | 实验详情 |
| `/experiments/:id/cancel` | POST | 取消运行 |
| `/experiments/:id/replay?cursor=0&limit=1000` | GET | 有界历史事件页；按 `next_cursor` 翻页直到 `null` |
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
