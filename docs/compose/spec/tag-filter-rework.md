---
feature: tag-filter-rework
status: delivered
updated: 2026-10-23
branch: feat/tag-filter-rework
commits: 未提交（本地变更）
---

# 标签筛选系统重做：作用域收窄 + 分组计数 + 任一/全部 + 状态保持

## Report

**What was built** — 时间浏览页的标签筛选系统从「平铺 17 个 chip + 纯 OR」重做为**模式 / 内容 / 结构三组 facet**：

1. **识别精度**：`hero_trial`、`ptr`、`stadium`、`workshop` 四条规则从 WHOLE 收窄为 TITLE_SECTIONS，删掉正文级误标（赛后试玩反馈、`Unlike the PTR` 对比句、Bug 修复里的 Stadium / Custom Game 提及、2017 Summer Games 的 “new stadium” 球场）。`quick_play_hacked` / `april_fools` / `experiment_6v6` / `community_created` 保持 WHOLE，保留「常规标题 + 模式内容块」的混合补丁徽章。
2. **模式 facet 以 `mode` 为权威**：模式组直接列出 7 个非常规模式（含此前无法筛选的「公告」），谓词为 `p.mode === key || categories.includes(key)`；内容组为 `CATEGORY_ORDER` 去掉 6 个模式键后的 9 类；结构组为 `hero_changes`。不新增 category 规则、不升 `schema_version`。
3. **可读的筛选 UI**：chip 按组显示，带命中数量；多选时出现「已选」摘要、「任一 / 全部」分段开关与「清空筛选」；`match=all` 空结果提供「改为匹配任一」。
4. **状态**：`?cat=…&match=all` 可分享；旧 `?cat=a,b` 链接仍按 OR 解释；补丁条目的链接携带筛选，补丁页「← 按时间浏览」与中英切换均保留筛选。
5. **移动端**：720px 以下出现「筛选（N）」收起/展开按钮，未筛选时默认收起；sticky 高度由现有 `ResizeObserver` 更新。

- **数据实证**（350 条索引）：`hero_trial` 9→5、`ptr` 3→2、`stadium` 61→57、`workshop` 98→56；其余 11 类计数不变（QP 7 / 愚人节 5 / 6v6 3 / 社区 4 / 活动 52 / 赛季 28 / 新英雄 29 / 新地图 12 / 街机 20 / 联赛 10 / 联动 15）。无标签补丁 143→162；chip 18 个（全部 + 7 模式 + 9 内容 + 英雄改动）。模式 facet 计数：QP 7 / 愚人节 5 / 6v6 3 / 试玩 5 / PTR 2 / 社区 4 / 公告 2。
- **正例保留**：`p-2026-01-08-1` 仍有 `quick_play_hacked` 且 mode=standard；`p-2026-10-06-1` stadium；`p-2025-03-19-1` hero_trial；`en-2018-03-29-1` ptr；`en-2019-07-16-1` workshop。
- **误标移除**：`en-2017-08-08-1` / `en-2026-03-31-1` 无 stadium；`p-2025-12-09-1` / `en-2024-08-20-1` 无 hero_trial；`en-2020-02-25-1` 无 ptr；`p-2026-04-14-1` / `p-2026-08-11-1` 无 workshop。

**Verification** — `python -m pytest -q` → **308 passed**；`node tools/_smoke_web.js` → **ALL WEB ASSERTIONS OK**（18 chips、分组标签、计数与数据谓词一致、announcement=2、任一/全部、URL、补丁链接/返回链接保持）；`npx --yes -p playwright@1.61.0 node tools/_spa_check.js` → **ALL SPA ASSERTIONS OK**（筛选→补丁→返回无刷新、状态恢复、6/350、无 console/CSP 错误）；`npx --yes -p playwright@1.61.0 node tools/_layout_check.js` → **ALL LAYOUT ASSERTIONS OK**（1280/390 分组、计数、摘要、URL 种子、旧 ?cat OR、移动端收起、无横向溢出）；`python tools/rebuild.py --data data` 三跑字节幂等，数据侧仅 `data/patches_index.json` 变化。

**Journey log** — ① 正文级误标是主要噪声：Stats 里 “during her hero trial”、`Unlike the PTR`、`bug fixed in Stadium` 都不是内容分类；把 4 条规则改成 TITLE_SECTIONS 后 51 个标签被移除，且逐条确认均为正文提及。② 模式不应再依赖 category 短语规则：`announcement` 只有 mode 字段可筛，因此模式 facet 直接读 `mode`，同时保留 mixed-content 的 `categories` 兜底。③ URL 里的逗号会被 `URLSearchParams` 编码成 `%2C`，Playwright/smoke 断言必须 decode 后再比较。④ smoke DOM shim 没有 `querySelectorAll`，组标签因此作为 `#cat-chips` 的直接子元素，测试按 `dataset.cat !== undefined` 过滤。⑤ 移动端默认收起后，Playwright 不能 `waitForSelector` 默认可见状态，须用 `state: "attached"`。

## [S1] Problem

时间浏览页的标签筛选存在四类问题：

1. **误标**：`stadium` 61 条中 2017-08-08 的 “new stadium”（Lucioball 球场）和 3 条 Bug 修复正文被误标；`workshop` 98 条中 42 条只是 Bug 修复正文提到 Custom Game；`hero_trial` 9 条中 4 条是赛后反馈；`ptr` 3 条中 1 条是 “Unlike the PTR” 对比句。
2. **模式不完整**：`announcement` 有 mode 徽章但没有 chip，2 条公告无法筛选。
3. **语义模糊**：多选是 OR，但摘要写成「筛选：活动 / 新英雄」，没有「任一 / 全部」入口；chip 无数量、无分组。
4. **状态丢失**：从补丁详情点「← 按时间浏览」会丢失筛选；移动端 17 个 chip 的 sticky 区过高。

## [S2] Design

### D1 作用域（`src/ow2_patch/categories.py`）

| key | 旧 | 新 | 依据 |
|---|---|---|---|
| `hero_trial` | WHOLE | TITLE_SECTIONS | 正文试玩反馈不是试玩补丁 |
| `ptr` | WHOLE | TITLE_SECTIONS | 正文 PTR 对比句不是 PTR 补丁 |
| `stadium` | WHOLE | TITLE_SECTIONS | 正文 Bug 修复/球场不是角斗领域 |
| `workshop` | WHOLE | TITLE_SECTIONS | 正文 Bug 修复不是工坊更新 |

保留 `quick_play_hacked` / `april_fools` / `experiment_6v6` / `community_created` 为 WHOLE；`categorize_content()` 语义不变；不新增 category 规则。

### D2 前端 facet（`web/app.js`）

- `MODE_FILTER_KEYS`（7 个非常规模式，固定顺序）、`CONTENT_FILTER_KEYS`（`CATEGORY_ORDER` 减去模式键）、`FILTER_GROUPS`（模式/内容/结构）、`FILTER_KEYS`、`FILTER_KEY_SET`、`FILTER_LABEL = {…CATEGORY_LABEL, …MODE_LABEL}`。
- `filter = { selected: Set, match: "any" | "all" }`；`keyMatches` 按模式（`mode` ∪ mixed categories）/内容（categories）/结构（standard + has_hero_changes）分别判定；`filterMatches` 按 `match` 做 `some`/`every`。
- `setFilter(keys, match)`、`setMatch(match)`、`getFilter()`、`getFilterMatch()`；单标签自动规范化为 `any`。

### D3 UI / 可访问性（`web/app.js` + `web/style.css`）

- `buildCategoryChips`：`全部` + 每组标签 + chip；组标签是 `#cat-chips` 直接子元素（兼容 smoke shim）；chip 带 `data-cat`、`data-count`、`aria-label="组：标签，N 个补丁"` 与 `.chip-count`。
- `#filter-summary`：已选标签、`任一/全部` 分段（仅 ≥2 选择时显示）、`清空筛选`；空结果按 `match` 给出说明与「改为匹配任一」。
- `#patch-count`：`共 N / 350 条补丁 · 匹配任一/同时包含：…`。
- 720px 以下 `#filter-toggle` 可收起 chips；未筛选且窄屏时默认收起，`aria-expanded`/`aria-controls` 同步。
- `#patch-count` 保持 `aria-live="polite"`；chip `aria-pressed`；match 按钮 `aria-pressed`；不引入内联脚本，CSP 不变。

### D4 URL / 跨页状态

- `cat` 按 `FILTER_KEYS` 规范排序，`match=all` 仅在 ≥2 选择时输出；旧 `?cat=a,b` 仍为 OR。
- `patchHref` 给补丁链接附加 `cat`/`match`；`patch.html` 返回链接 `#back-index` 与 `buildLangSwitch` 读取并保留；浏览器 back/forward 由现有 SPA 路由恢复。

### D5 测试

- `tests/test_categories.py`：四条规则的作用域正/负例。
- `tests/test_pairing.py`：真实数据计数（5/2/57/56）、误标 ID 消失、正例保留。
- `_smoke_web.js`：18 chips、组标签、chip 计数与数据谓词一致、announcement、任一/全部、URL、补丁链接/返回链接、AND 空状态。
- `_spa_check.js`：筛选→补丁→返回无刷新且状态恢复。
- `_layout_check.js`：1280/390 分组、计数、摘要、URL 种子、旧 ?cat OR、移动端收起/展开、无横向溢出。
- `rebuild` 双跑/三跑字节幂等，数据侧仅 `patches_index.json`。

## [S3] Out of Scope

- entries.html / hero.html 的检索与筛选。
- `mode` 分类逻辑、hero/entries/values 数据过滤、数据 schema。
- 新内容标签（热修/皮肤/神话/平衡等）与标签说明 tooltip。
- 视觉大改版、页面转场、服务端/部署流程。

## Tasks

- [x] T1: 作用域收窄 + docstring — acceptance: `test_categories.py` 正负例全绿（covers: D1）
- [x] T2: 重建 `patches_index.json` — acceptance: 计数 5/2/57/56、仅该文件变化、三跑幂等（covers: D1）
- [x] T3: facet/计数/任一全部/摘要/移动端 — acceptance: 18 chips、分组、计数、空状态、a11y（covers: D2 D3）
- [x] T4: URL/补丁链接/返回/语言切换保持 — acceptance: `?cat`/`match=all`、返回恢复、旧链接 OR（covers: D4）
- [x] T5: smoke/spa/layout 回归 — acceptance: 三脚本全绿（covers: D5）
- [x] T6: README/规格定稿 — acceptance: 文档含设计、计数与验证记录（covers: 全部）
