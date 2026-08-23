---
feature: ow1-season-launches
status: delivered
updated: 2026-08-23
branch: feat/ow1-season-launches
commits: d3b481a..35e5370
---

# OW1 竞技赛季新赛季标记

## Report

**What was built** — 「新赛季」徽章此前只覆盖 OW2 时代（2022-10 起）；本特性把 **OW1 竞技赛季发布** 中**文本可证**的 S1-S3 补录为 `season`：`en-2016-06-28-1`（S1 竞技模式上线，block "New Feature: Competitive Play"）、`en-2016-09-02-1`（S2，block 标题 "Competitive Play Season 2"）、`en-2016-11-15-1`（S3，block 标题 "Season 3 of Competitive Play"）。season 计数 **24 → 27**（24 个 OW2 赛季 + 3 个 OW1）。规则层零改动——全量审计证实规则扩展（TITLE_SECTIONS/WHOLE）只多抓 2 个开赛却重新引入 3+ 个 OW1 误判（街机/中赛季），且 S4-S23 在归档补丁中根本无赛季开赛文本，故采用手动标记（用户确认范围）。

- **负例守卫**：OW1 街机/活动赛季补丁（`en-2021-09-07-1` Lockout Elimination S4、`en-2021-12-16-1` No Limits S2）保持无 `season`（其文本在非首节，TITLE_FIRST 作用域外）。
- **review**：general-7 全部验收标准 MET、0 critical；1 项非关键（spec 措辞）已修复。

**Verification** — `pytest -q` → 260 passed（real-data 不变量新增 3 正例 + 2 负例 + 计数 27 断言）；`node tools/_smoke_web.js` → ALL WEB ASSERTIONS OK（chipCount 16 / event 52 / entryCards 904 均不变）；`python tools/rebuild.py --data data` 双跑字节幂等（数据 diff 仅 manual_categories.json + patches_index.json 各 3 行）；`npx --yes -p playwright node tools/_layout_check.js` → 12/12；真实浏览器：S1-S3 三个 2016 补丁条目显示「新赛季」徽章，两个街机赛季补丁无徽章，OW2 补丁不受影响。

**Journey log** — ① OW1 竞技赛季 23 个中仅 S2/S3 有编号开赛文本（block 标题）、S1 为模式上线（无编号）、S4-S23 在补丁中**完全无**赛季文本（开赛发生在补丁之间）——文本识别上限就是 3 条，规则扩展换不来第 4 条。② 规则扩展的性价比审计：TITLE_SECTIONS 多抓 2 个开赛、代价是 3 个 OW1 误判（"Season 19 Map Pool" 中赛季通知、Lockout/No Limits 街机赛季），WHOLE 全量 29 个误判——手动标记是唯一零误判路径。③ manual_categories.json 按 index `id` 键追加合并（未知键丢弃），与规则类别叠加不互斥——未来召回修正的通用扩展点。

## [S1] Problem

时间浏览页的「新赛季」徽章目前只覆盖 OW2 时代（2022-10 起，24 个标注全为 OW2 赛季发布）；OW1 竞技赛季（2016-2022，S1-S23）未被识别。原因：season 规则为 title+首节标题作用域（TITLE_FIRST），而 OW1 时代唯一有开赛文本的 S2/S3 其表述在 **block 标题** 中（"Competitive Play Season 2" / "Season 3 of Competitive Play"），作用域之外。

## [S2] Design

### D1 数据：manual_categories.json 增加 3 条 OW1 season 标记

用户已确认：仅标记**文本可证**的 S1-S3（零误判风险），S4-S23 不标记（归档补丁中无任何赛季开赛文本，语义外推明确排除）。

```json
"en-2016-06-28-1": ["season"],   // S1：竞技模式上线（block "New Feature: Competitive Play"，无赛季编号）
"en-2016-09-02-1": ["season"],   // S2：block 标题 "Competitive Play Season 2"
"en-2016-11-15-1": ["season"],   // S3：block 标题 "Season 3 of Competitive Play"
```

- 规则层（categories.py `season` 的 TITLE_FIRST + `continues` 守卫）**不动**——审计证实 TITLE_SECTIONS/WHOLE 扩展会重新引入 OW1 街机/中赛季误判（en-2019-11-05 "Season 19 Map Pool"、en-2021-09-07 Lockout 赛季、en-2021-12-16 No Limits 赛季等）。
- rebuild 重生成 `data/patches_index.json`：season 计数 24 → **27**。

### D2 测试（tests/test_pairing.py real-data 不变量）

`test_real_patches_index_categories_invariants` 追加：
- `en-2016-06-28-1` / `en-2016-09-02-1` / `en-2016-11-15-1` categories 含 `season`；
- 街机赛季补丁 `en-2021-09-07`（Lockout）、`en-2021-12-16`（No Limits）**不含** `season`；
- season 总数 27。

## [S3] Out of Scope

- S4-S23 的标记（归档补丁无开赛文本；用户明确排除）。
- 规则层扩展（TITLE_SECTIONS/WHOLE 引入 OW1 误判，审计证实不可行）。
- 前端/其他数据文件（categories 不向下游供数）。

## Tasks

- [x] T1: spec 文档 + worktree — acceptance: 本文档含设计与任务；`.worktrees/ow1-season-launches` 分支 `feat/ow1-season-launches`（covers: 全部）
- [x] T2: manual_categories.json +3 + rebuild + 测试断言 — acceptance: pytest 新增断言全绿、season 计数 27、仅 patches_index.json 变化（covers: D1 D2；depends: T1）
- [x] T3: 全量验证 — acceptance: pytest/smoke/layout 全绿、rebuild 双跑幂等、真实浏览器 3 个 OW1 补丁显示新赛季徽章且街机赛季无徽章（covers: D1 D2；depends: T2）
- [x] T4: 独立 review — acceptance: 0 critical（covers: 全部；depends: T3）
- [x] T5: 独立 review + 规格定稿 — acceptance: status: delivered、Report 填毕（covers: 全部；depends: T4）
