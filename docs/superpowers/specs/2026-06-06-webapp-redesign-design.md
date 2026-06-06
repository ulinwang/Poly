# PolyMetl 网站重构设计

- 日期：2026-06-06
- 状态：已确认，待实施
- 适用仓库：`polymetl/`（前端 `webapp/frontend`，TS 后端 `backend`，Python agent 层 `agent/`）

## 背景与问题

当前网站正处在重构中（Python 后端 → TypeScript Fastify 后端）。诊断结论：

- **后端 API 正常**：`/api/v1/markets`、`/experiments`、`/providers`、`/settings/api` 均返回 200，Vite 代理 `/api`→`:8765` 正常。
- **前端显示异常的根因**：Tailwind v3/v4 配置冲突。实际生效的 `postcss.config.js` 用的是 v4 引擎（`@tailwindcss/postcss@4.3.0`），但 `index.css` 用 v3 的 `@tailwind` 指令、自定义调色板定义在 `tailwind.config.js`。Tailwind v4 默认不读 JS config，导致源码中用到的 34 个自定义颜色类（`bg-surface-*`、`bg-primary-*` 等，遍布 Sidebar/MainLayout/TopNav）全部没有生成 CSS——页面骨架在、配色全失。开发服务器(5173)与打包的 dist(8765)同样受影响。残留的 `postcss.config.mjs` 是一次被 `.js` 抢先加载而未生效的修复尝试。
- **架构评估**：分层方向正确（routes → services → db 单向依赖、无循环依赖、SQL 参数化），但存在：`routes/experiments.ts` 偏胖、provider 元数据散落两处、`runner.ts:67` 硬编码本机绝对路径、API key 明文存 SQLite 且回传前端。

## 目标

1. 修复前端显示（迁移到 Tailwind v4，配置统一）。
2. 重构前端信息架构与页面流程，贴近 Polymarket 视觉。
3. 后端 provider 层参考 [litellm](https://github.com/BerriAI/litellm) 统一多供应商接入。
4. 修复安全/可复现问题（硬编码路径、明文 key）。

非目标（YAGNI）：数据库迁移框架、缓存可观测性、Redis、生产部署加固等——本次不做。

### 命名与清理（已确认）

- **品牌改名为 "Poly"**：前端 `TopNav.tsx`、`index.html` 标题、`pyproject.toml` 包名等 "PolyMetl"/"polymetl" 字串改为 "Poly"/"poly"。**不改代码 import（Python 按 `agent`/`environment`/`webapp` 导入，与名称无关），不改目录名。**
- **暂不删除**：`webapp/backend/`（已废弃 Python 后端）、`webapp/server.py`/`explorer.py`（v12 旧后端）、根目录 `polymetl-backup-20260603-152256/`（6.8G 备份）全部保留。
- **数据分析流水线不动**：`experiments/`（含 `analysis/`、`plots/`）、`scripts/`（thesis_v14/v15 分析、`clustering/`、RQ 作图、`build_thesis_docx`/`render_thesis`）、`viz/`、`comparison/` 是论文研究主体，与网站解耦（网站不 import 它们），本次重构完全不触碰。

## 设计

### A. 前端样式基建 — Tailwind v4 迁移

- 删除 `webapp/frontend/postcss.config.js`，保留单一配置文件，插件仅用 `@tailwindcss/postcss`；从 `package.json` 移除 `tailwindcss@3`（保留 `@tailwindcss/postcss@4`、`autoprefixer`、`postcss`）。
- `src/index.css`：`@tailwind base/components/utilities` → `@import "tailwindcss";`。
- 自定义调色板（primary、surface、success/warning/danger/info）从 `tailwind.config.js` 迁移到 CSS 的 `@theme { --color-primary-500: …; --color-surface-900: …; }`；`@layer components`（card/btn/badge 等）保留。
- darkMode 改用 v4 的 class 策略写法；`@layer base` 中的 `html.dark` 规则保留。
- 重新 `npm run build` 生成 dist，使 8765 直接访问也恢复正常。
- **此项为地基，最先实施。** 验证标准：编译产物中能找到 `bg-surface-900`、`bg-primary-100` 等自定义颜色规则；浏览器中侧边栏/导航配色正确。

### B. 信息架构 + 页面流程

侧边栏三项固定导航：**浏览 / 实验 / 设置**。

- **支持展开/收缩**：展开态显示「图标＋文字」，收缩态只显示图标（hover tooltip）；顶部 toggle 切换；收缩状态持久化（沿用 settings store 的 `sidebarCollapsed`）。

主流程四步：

1. **浏览市场** `/markets`：Polymarket 风格卡片网格 + 分类筛选。
2. **市场详情** `/markets/:slug`：市场信息 + 「该市场已有实验」列表（可直接点开观察）+ 【＋ 新建实验】按钮。移除当前内联在此页的参数表单。
3. **参数配置整页** `/markets/:slug/new`（新增路由，非弹窗）：见 F。确认后创建实验并跳转观察页。
4. **实验观察页** `/experiments/:id`：见 D。

侧边栏「实验」→ 跨市场实验总列表（沿用 `ExperimentManager`，路由 `/experiments`）；「设置」→ `/settings/*`（选择供应商 + API）。

### C. 前端视觉

非侧边栏区域参考 Polymarket 截图：浅色主题、卡片网格、分类 chips、Yes/No 配色。属"风格参考"，非像素级复刻。侧边栏为本项目自有设计。

### D. 实验观察页（布局方案 A）

- **顶部**：可横向滑动的 Agent 并排小窗，每个显示 头像＋编号＋盈亏%＋迷你走势线，点选高亮；左右滑动切换。
- **主区**：宏观市场结果（价格/概率走势图 + 关键指标）。
- **右侧抽屉**：选中 Agent 的详情——**思考文本（LLM 推理过程）＋ 决策记录 ＋ 状态 ＋ 持仓**。未选中时抽屉收起，宏观图表占满。

### E. 后端 provider 层 — litellm 进 Python agent 层

- `agent/decision/llm.py` 用 `litellm.completion()` 替换直连 `openai` SDK：
  - 保留两个入口的语义：文本模式（persona 生成）与 function-tool 模式（每 tick 交易决策）。
  - 保留 tool-calling、DeepSeek thinking 透传（litellm 支持 provider 专有参数透传）、重试逻辑。
  - 函数命名去 DeepSeek 化，改为中性（如 `call_llm` / `call_llm_with_tools`），通过 provider+model+base_url 路由。
- **provider 目录单一数据源**：定义供应商/模型/base_url/是否需要 key 的清单，前端设置页与 Python 推理共用（避免现状两处重复）。
- TS 后端 `/api/v1/settings/test` 改为走 litellm 的极小调用做连通性测试，去掉散落的 provider 默认值与硬编码跳过逻辑。
- 接受新增 Python 依赖 `litellm`，写入 `pyproject.toml` 与 lock（对论文复现影响小且可控）。

### F. 接口变更（数据流）

`ExperimentConfig` 扩展字段：

- 现有：`slug`、`n_agents`、`n_ticks`、`persona_set`
- 新增：`provider`、`model`、`temperature`、`seed`
- **每次实验单独选供应商/模型**：配置页默认带出全局设置的值，可改（便于做不同模型对照研究）。
- **API key 不走前端**：后端按所选 provider 从加密存储注入到 Python 子进程。
- `seed` 用于固定 Python 侧随机性，支撑可复现。
- `runner.ts` 将以上参数通过 stdin（JSON）传给 Python，沿用现有 JSON over stdin/stdout 协议。

### G. 后端安全 / 可复现修复

- `services/runner.ts:67` 硬编码 `cwd: '/Users/moonshot/Projects/Poly/polymetl'` → 改为基于 `__dirname` 计算的仓库根路径，或读 env `POLYMETL_ROOT`。
- API key：
  - 不再明文存 SQLite——用对称加密（envelope/AES），主密钥来自 env（如 `POLYMETL_SECRET`）。
  - `/settings/api` GET 不再回传明文 key，仅返回 `api_key_set: boolean`（前端 `ApiSettings` 类型相应调整）。
  - 仅在创建实验注入子进程、或连通性测试时在内存中解密使用。

## 实施分期（每期独立可验证）

1. **Tailwind v4 迁移** —— 地基，先恢复显示。
2. **后端安全修复** —— 硬编码路径 + key 加密。
3. **litellm provider 层** —— Python 改造 + provider 目录统一 + `/settings/test` 改造。
4. **前端流程重构** —— 侧边栏（展开/收缩）+ 配置整页 + 路由调整。
5. **观察页 + Polymarket 视觉** —— 观察页方案 A + 浏览/详情视觉。

## 测试策略

- 后端沿用 vitest（`backend/src/tests`、`runner.test.ts`）；litellm 改造层加 mock 测试（不打真实 API）。
- 前端沿用 hooks/stores 测试；新增页面/路由加基本渲染测试。
- 每期结束手动跑一次完整链路（浏览 → 配置 → 观察）确认，关键截图留档。
- Tailwind 迁移后以"编译产物含自定义颜色规则"为客观验收点。

## 风险与权衡

- litellm 为较重依赖：换取多供应商统一与重试/fallback，符合用户明确要求；通过 lock 固定版本控制复现风险。
- key 加密引入 env 主密钥的管理成本：相对明文存储与回传前端，安全收益显著。
- 前端流程改动较大：分期推进，先以 Tailwind 修复让现有页面可用，再逐页重构。
