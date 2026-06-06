# Tailwind v4 迁移 + 品牌改名 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把前端 Tailwind 从 v3/v4 混用修正为纯 v4，使 34 个自定义颜色类重新生成，恢复页面配色；同时把用户可见品牌名 PolyMetl 改为 Poly。

**Architecture:** 实际生效的引擎已是 Tailwind v4（`@tailwindcss/postcss@4.3.0`）。迁移即把 CSS 入口、暗色变体、自定义调色板从 v3 写法（`@tailwind` 指令 + `tailwind.config.js`）改为 v4 写法（`@import "tailwindcss"` + `@custom-variant` + `@theme`），删除 v3 残留与重复配置，最后重新构建 dist。品牌改名只动用户可见字串与包名，不动任何代码 import 或目录名。

**Tech Stack:** Vite 8、Tailwind CSS v4、PostCSS、React 19、TypeScript。

**前置说明（执行者必读）：**
- 工作目录：所有前端命令在 `webapp/frontend/` 下执行；仓库根为 `/Users/moonshot/Projects/Poly/polymetl`。
- 当前分支应为 `refactor/webapp-redesign`（已存在）。
- 验收的客观标准：构建产物 CSS 中能搜到自定义颜色规则（如 `surface-900`、`primary-100`）。迁移前这些是 0 条。
- 注意已知 v4 破坏性变更：默认边框色从 gray-200 改为 currentColor；本项目布局组件多用显式 `border-surface-*`，影响小，若个别边框变色在 Task 7 视觉检查时记录。

---

## File Structure

- `webapp/frontend/postcss.config.js` — 修改：v4 唯一 PostCSS 插件
- `webapp/frontend/postcss.config.mjs` — 删除：重复配置（v3 写法，未生效）
- `webapp/frontend/tailwind.config.js` — 删除：v4 不再用 JS config，调色板迁入 CSS
- `webapp/frontend/src/index.css` — 修改：v4 入口 + 暗色变体 + `@theme` 调色板
- `webapp/frontend/package.json` — 修改：移除 `tailwindcss@3`、`autoprefixer`
- `webapp/frontend/index.html` — 修改：`<title>` 改名
- `webapp/frontend/src/components/layout/TopNav.tsx` — 修改：品牌字串改名
- `pyproject.toml` — 修改：包名 `polymetl` → `poly`

---

## Task 1: 清理重复/过时的构建配置

**Files:**
- Modify: `webapp/frontend/postcss.config.js`
- Delete: `webapp/frontend/postcss.config.mjs`

- [ ] **Step 1: 把 postcss.config.js 改成 v4 唯一插件**

`webapp/frontend/postcss.config.js` 全文替换为：

```js
export default {
  plugins: {
    '@tailwindcss/postcss': {},
  },
}
```

（v4 自带前缀处理，不再需要 autoprefixer。）

- [ ] **Step 2: 删除重复的 postcss.config.mjs**

Run:
```bash
rm webapp/frontend/postcss.config.mjs
```

- [ ] **Step 3: 确认只剩一个 postcss 配置**

Run:
```bash
ls webapp/frontend/postcss.config.*
```
Expected: 只输出 `webapp/frontend/postcss.config.js`

---

## Task 2: 迁移 index.css 到 v4（入口 + 暗色变体 + 调色板）

**Files:**
- Modify: `webapp/frontend/src/index.css`

- [ ] **Step 1: 替换文件头部的 @tailwind 指令与暗色策略**

把 `webapp/frontend/src/index.css` 顶部第 1–3 行：

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

替换为：

```css
@import "tailwindcss";

/* class 策略暗色模式：让 dark: 工具类响应 <html class="dark">，
   而不是 v4 默认的 prefers-color-scheme 媒体查询 */
@custom-variant dark (&:where(.dark, .dark *));

/* 自定义调色板（原 tailwind.config.js theme.extend.colors 迁移而来） */
@theme {
  --color-primary-50: #f0fdf9;
  --color-primary-100: #ccfbf1;
  --color-primary-200: #99f6e4;
  --color-primary-300: #5eead4;
  --color-primary-400: #2dd4bf;
  --color-primary-500: #14b8a6;
  --color-primary-600: #0d9488;
  --color-primary-700: #0f766e;
  --color-primary-800: #115e59;
  --color-primary-900: #134e4a;

  --color-surface-0: #ffffff;
  --color-surface-50: #f8fafc;
  --color-surface-100: #f1f5f9;
  --color-surface-200: #e2e8f0;
  --color-surface-300: #cbd5e1;
  --color-surface-400: #94a3b8;
  --color-surface-500: #64748b;
  --color-surface-600: #475569;
  --color-surface-700: #334155;
  --color-surface-800: #1e293b;
  --color-surface-900: #0f172a;

  --color-success: #22c55e;
  --color-warning: #f59e0b;
  --color-danger: #ef4444;
  --color-info: #3b82f6;

  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;

  --radius-xl: 1rem;
  --radius-2xl: 1.5rem;
}
```

第 5 行起的 `@layer base { ... }` 和 `@layer components { ... }` 两块**保持不变**（它们用的是写死的 hex 值，v4 下照常工作）。

- [ ] **Step 2: 确认 @tailwind 指令已无残留**

Run:
```bash
grep -n "@tailwind " webapp/frontend/src/index.css || echo "OK: no v3 directives left"
```
Expected: 输出 `OK: no v3 directives left`

---

## Task 3: 删除 tailwind.config.js

**Files:**
- Delete: `webapp/frontend/tailwind.config.js`

- [ ] **Step 1: 删除 JS 配置（v4 自动扫描内容，调色板已迁入 CSS）**

Run:
```bash
rm webapp/frontend/tailwind.config.js
```

- [ ] **Step 2: 确认没有其他文件还在引用它**

Run:
```bash
grep -rn "tailwind.config" webapp/frontend --include=*.ts --include=*.js --include=*.mjs --include=*.json 2>/dev/null | grep -v node_modules || echo "OK: no references"
```
Expected: 输出 `OK: no references`（若有命中，说明有文件硬引用了 config，需在该处移除）

---

## Task 4: 移除 package.json 里的 v3 依赖

**Files:**
- Modify: `webapp/frontend/package.json`

- [ ] **Step 1: 从 devDependencies 删除两行**

在 `webapp/frontend/package.json` 的 `devDependencies` 中删除这两行：

```json
    "autoprefixer": "^10.5.0",
```
```json
    "tailwindcss": "^3.4.19",
```

保留 `@tailwindcss/postcss`、`postcss`、`vite` 等其余依赖不变。

- [ ] **Step 2: 重新安装以更新 lockfile 并移除多余包**

Run:
```bash
cd webapp/frontend && npm install
```
Expected: 安装成功，无报错；`package-lock.json` 更新。

- [ ] **Step 3: 确认 tailwindcss@3 已不在依赖树顶层**

Run:
```bash
cd webapp/frontend && cat node_modules/tailwindcss/package.json 2>/dev/null | grep '"version"' || echo "removed"
```
Expected: 输出 `4.x` 版本号（作为 `@tailwindcss/postcss` 的传递依赖存在，不再是 3.4.19），或 `removed`。**不应再是 3.4.19。**

---

## Task 5: 构建并验证自定义颜色已生成（客观验收点）

**Files:** 无（验证步骤）

- [ ] **Step 1: 全新构建前端**

Run:
```bash
cd webapp/frontend && npm run build
```
Expected: `tsc -b && vite build` 成功，生成 `dist/assets/*.css`，无 PostCSS/Tailwind 报错。

- [ ] **Step 2: 在构建产物中搜自定义颜色规则**

Run:
```bash
grep -o 'surface-900\|primary-100\|primary-600\|bg-success' webapp/frontend/dist/assets/*.css | sort -u
```
Expected: 至少能命中 `surface-900`、`primary-100`、`primary-600` 等（迁移前为 0）。**若仍为空，说明 @theme 未生效，停下排查（常见原因：postcss 配置未指向 @tailwindcss/postcss，或 index.css 仍有 @tailwind 残留）。**

- [ ] **Step 3: 确认暗色变体已按 class 生成**

Run:
```bash
grep -o '\.dark' webapp/frontend/dist/assets/*.css | head -1
```
Expected: 能命中 `.dark`（证明 `@custom-variant dark` 生效，`dark:` 工具类绑定到 `.dark` 类而非媒体查询）。

- [ ] **Step 4: 提交 Tailwind 迁移**

Run:
```bash
cd /Users/moonshot/Projects/Poly/polymetl
git add webapp/frontend/postcss.config.js webapp/frontend/src/index.css webapp/frontend/package.json webapp/frontend/package-lock.json
git rm webapp/frontend/postcss.config.mjs webapp/frontend/tailwind.config.js
git commit -m "$(cat <<'EOF'
fix(frontend): migrate Tailwind to v4 — restore custom palette + class dark mode

Engine was already v4 but config/CSS were v3 (@tailwind directives + JS config),
so 34 custom surface-*/primary-* color utilities generated no CSS. Move palette to
@theme, switch entry to @import "tailwindcss", add @custom-variant dark for
class-based dark mode, remove duplicate postcss.config.mjs and tailwindcss@3.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 品牌改名 PolyMetl → Poly（用户可见字串）

**Files:**
- Modify: `webapp/frontend/index.html:7`
- Modify: `webapp/frontend/src/components/layout/TopNav.tsx:36`

- [ ] **Step 1: 改页面标题**

把 `webapp/frontend/index.html` 第 7 行：

```html
    <title>PolyMetl</title>
```

改为：

```html
    <title>Poly</title>
```

- [ ] **Step 2: 改顶栏品牌字串**

把 `webapp/frontend/src/components/layout/TopNav.tsx` 第 36 行的 `PolyMetl`（位于 `<span>` 内）改为 `Poly`。改后该 span 内容为：

```tsx
              Poly
```

- [ ] **Step 3: 确认前端源码内已无 PolyMetl 字串**

Run:
```bash
grep -rn "PolyMetl" webapp/frontend/src webapp/frontend/index.html || echo "OK: brand renamed"
```
Expected: 输出 `OK: brand renamed`

---

## Task 7: 包名改名 polymetl → poly（不影响 import）

**Files:**
- Modify: `pyproject.toml:2`

- [ ] **Step 1: 改包名**

把 `pyproject.toml` 第 2 行：

```toml
name = "polymetl"
```

改为：

```toml
name = "poly"
```

- [ ] **Step 2: 验证 Python 代码 import 不受影响**

Run:
```bash
cd /Users/moonshot/Projects/Poly/polymetl && .venv/bin/python3 -c "import agent, environment, webapp; print('imports OK')"
```
Expected: 输出 `imports OK`（顶层包名是 `agent`/`environment`/`webapp`，与发行包名无关，改名不破坏运行）。

- [ ] **Step 3: 视觉自检（开发服务器）**

确认前端 dev server 在 `:5173`（若未运行：`cd webapp/frontend && npm run dev`）。在浏览器打开 http://localhost:5173 ，检查：侧边栏/导航有正确底色与文字色（不再是无样式裸排版）、暗色切换正常、顶栏显示 "Poly"。记录任何因 v4 默认边框色变化导致的边框异常。

- [ ] **Step 4: 提交改名**

Run:
```bash
cd /Users/moonshot/Projects/Poly/polymetl
git add webapp/frontend/index.html webapp/frontend/src/components/layout/TopNav.tsx pyproject.toml
git commit -m "$(cat <<'EOF'
chore: rename brand PolyMetl -> Poly (UI title, top nav, package name)

User-facing rename only. Python import packages (agent/environment/webapp) and
the polymetl/ directory name are unchanged.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review 结论

- **Spec 覆盖**：本计划覆盖 spec 的 A 节（Tailwind v4 迁移）与「命名与清理」中的品牌改名；未涉及的 B–G 节属后续各期，另立计划。
- **占位符**：无 TBD；每个代码步骤均给出完整内容与可执行命令。
- **关键风险已显式处理**：v4 class 暗色需 `@custom-variant dark`（Task 2）；v3 残留检测（Task 2 Step2 / Task 5 Step2）；v4 默认边框色变化在 Task 7 视觉检查记录。
