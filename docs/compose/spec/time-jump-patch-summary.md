---
feature: time-jump-patch-summary
status: in-progress
updated: 2026-08-22
branch: feat/time-jump-patch-summary
commits: # filled at delivery
---

# 时间浏览页快速跳转 + 补丁首节标题徽章

## Report

## [S1] Problem

时间浏览页（`web/index.html`，`initIndex()` 渲染）把所有年份（2016–2026，343 条补丁、124 个月区块）平铺成长页，用户想找某年某月的补丁只能手动滚动；且每条补丁只显示通用官方标题（"《守望先锋》补丁说明——日期"），无法一眼看出该补丁改了什么。另有徽章显示缺陷：`mode-community_created`（社区创造模式）徽章没有 CSS 背景色规则，与其它 mode 徽章样式不一致。

## [S2] Design

### D1 数据层：patches_index 增加首节标题字段（src/ow2_patch/pairing.py）

`build_patches_index` 的每个条目增加 `first_section_en` / `first_section_cn`：该侧补丁 `sections[]` 中**第一个非空 `title`**（无则 `""`）。复用现有 `_section_titles()`（文件缺失返回 `[]`、无标题 section 得 `""`），在 `_pair_mode` 处把两侧读取结果捕获为局部变量，避免重复 IO。镜像现有 `title_en`/`title_cn` 模式：pair 两侧都填，unpaired 只填对应侧。字段为纯增量，所有既有消费者（app.js 按 key 读取、pipeline/entries 只取 mode/patch_id）不受影响。

### D2 前端：快速跳转条（web/index.html + web/app.js + web/style.css）

- `index.html` 在 `<main>` 内、`#patch-list` 之前加手工维护的 `<nav id="jump-bar" class="jump-bar" aria-label="快速跳转时间"></nav>`。
- `initIndex()` 渲染三个控件：`#jump-year`（年份倒序 `<select>`）、`#jump-month`（`<select>`，随所选年份重填，只列**有补丁的月份**，默认最新年 + 该年最新月）、跳转按钮。全部用 `createElement`/`appendChild` 构建（不用 `select.add()`/`prepend`，兼容 smoke DOM shim）。
- 年/月区块加锚点 id：`.year` → `id="year-YYYY"`，`.month` → `id="year-YYYY-month-MM"`；跳转执行 `document.getElementById(...)?.scrollIntoView?.({behavior:"smooth"})`（可选链保护无 scrollIntoView 环境）。
- CSS：`.jump-bar` 吸顶（`position: sticky; top: 0; z-index: 5;`，面板底色+边框）；`[id^="year-"] { scroll-margin-top: 56px; }` 抵消吸顶条；`html { scroll-behavior: smooth; }` 渐进增强。

### D3 前端：补丁首节标题徽章 + 徽章显示修复（web/app.js + web/style.css）

- 补丁条目在日期/站点/mode 徽章之后渲染章节徽章：按显示站点取值（`site === "cn" ? (p.first_section_cn || p.first_section_en) : (p.first_section_en || p.first_section_cn)`），非空时 `<span class="badge section" title="全文">标题</span>`（`esc()` 转义；`title` 属性存全文，视觉截断由 CSS 完成）。
- 新增 `.badge.section`：彩色药丸（绿色系 `rgba(129,199,132,.14)` / `#81c784`，与站点/模式/kind/attr 徽章区分），`max-width` + `overflow:hidden` + `text-overflow:ellipsis` + `white-space:nowrap`。
- 修复徽章背景缺失：新增通用兜底 `.badge.mode`（置于具体 mode 变体之前，同特异性靠定义顺序让具体变体覆盖）+ 显式 `.badge.mode-community_created`。
- `.patch-entry` 加 `flex-wrap: wrap; row-gap: 6px;`，`.patch-entry-title { min-width: 0; }`，保证徽章换行不破版。

### D4 测试

- `tests/test_pairing.py`：单测（tmp_path + fixture 补丁文件）——有 section 的 pair 取第一个非空标题、raw_text-only 得 `""`；真实数据不变量——每条目含 `first_section_en`/`first_section_cn` 两键，已知补丁（`en-2026-08-11-1`）首节标题非空。
- `tools/_smoke_web.js`：DOM shim `makeEl` 增加 `scrollIntoView(){}`、`add(){}` 空操作；`initIndex()` 后断言 `#jump-year` 有 11 个年份选项、`#jump-month` 已填充、补丁条目含 `.badge section`；保留 `indexPatches === 343`（跳转条位于 `#patch-list` 之外，不影响计数）。

### D5 迁移

仅 `tools/rebuild.py --data data` 重生成 `data/patches_index.json`（全离线；其余派生数据应字节稳定，若 git diff 出现多余改动需查因）。

## [S3] Out of Scope

- 跳转条的 URL 参数化（`?y=&m=` 分享链接）不在本期。
- 章节徽章不做标题过滤/智能缩写（字面取第一个非空 section 标题，长度截断仅视觉层）。
- 补丁列表不新增英雄名、补丁字数等其它摘要信息。

## Tasks

- [ ] T1: pairing.py `build_patches_index` 增加 `first_section_en/cn` —— acceptance: 单测通过；重生成后每条目含两键（covers: D1, D4）
- [ ] T2: `tools/rebuild.py --data data` 重生成索引 —— acceptance: `git diff` 仅新增字段，真实数据不变量测试通过（covers: D1, D5; depends: T1）
- [ ] T3: 前端跳转条 + 章节徽章 + CSS 修复 —— acceptance: smoke 测试新增断言通过；本地 serve 浏览器抽查跳转/徽章/community_created 背景（covers: D2, D3）
- [ ] T4: 测试补充（pairing 单测/不变量 + smoke shim/断言）—— acceptance: `pytest -q` 与 `node tools/_smoke_web.js` 全绿（covers: D4; depends: T1, T3）
- [ ] T5: 全量验证 + 独立审查 —— acceptance: pytest/smoke/layout/serve 通过，审查 0 critical（covers: D2, D3, D5）
