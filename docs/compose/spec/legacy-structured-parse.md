---
feature: legacy-structured-parse
status: designed
updated: 2026-08-21
branch: feat/legacy-structured-parse
commits: # filled at delivery
---

# Legacy 补丁结构化解析

## Report

## [S1] Problem

103 个 OW1 旧补丁（EN 2016-05-27 → 2020-01-28）当前降级为整块 `raw_text`，补丁详情页显示为无结构的纯文本，与新补丁（章节卡片、英雄块、头像/技能图标、项目符号、目录侧栏）格式差距大。英雄改动时间线也因此缺失 2016-2020 全部历史。

## [S2] Design

### D1 legacy 解析器（src/ow2_patch/parse.py）

- 触发：`_split_sections` 为空且 chunk 含 `--legacy` 类（或 h1-h4/strong-p 章节标题）→ `_parse_legacy_chunk(soup, site)`。
- 剥 `.PatchNotesTop` / `.PatchNotesPagination` chrome；首个标题（h1/h2/h3）为 patch.title。
- 按标题元素切分 section：h1-h4 标题 或 strong-only `<p>` 且去尾冒号文本 ∈ 章节词汇表（HERO UPDATES / BUG FIXES / GENERAL UPDATES / USER INTERFACE UPDATES / WORKSHOP UPDATES / MAP UPDATES / ARCADE / COMPETITIVE PLAY / PATCH FEATURES / KNOWN ISSUES / HERO GALLERY / PATCH INTRODUCTION / PATCH HIGHLIGHTS + 已观测事件名）。
- section 内逐元素：`is_dev`（两种 em 形态：`<strong><em>Developer Comments:</em></strong><em>…</em>` 与单 em `Developer Comment:`）→ 挂最近 hero/block；strong-only p 且 `is_known_hero` → HeroUpdate(name_en)；strong-only p 未命中 → GenericBlock(title)；`<ul>` → 有 hero 走 `parse_hero_list`，有 block 追加 `_list_lines(ul)`，否则并入 description；plain p 且 hero 且后随 ul（2019 形态）→ AbilityUpdate；其余 p → description。
- `parse_hero_list(ul, hero)`：顶层 li 有嵌套 ul → AbilityUpdate（子技能名扁平化：叶子改动并入父技能 changes，与现有 `_parse_ability` 一致）；无嵌套 → hero.general 行；改动行走 `_extract_numbers`。
- `sec.type = "hero_update" if sec.heroes else "generic_update"`（按内容判定）。
- 结构化补丁 `raw_text = None`；无法结构化的保持 raw_text fallback。

### D2 英雄判定（src/ow2_patch/names.py）

- 新增 `NameResolver.is_known_hero(name, site)`：命中 names.json（含 HERO_ALIASES）才 True；未知名不生成 auto-slug（现有 `hero()` 对未知名返回 auto-slug，"New Hero: Ana (Support)" 会被误判为英雄）。

### D3 哈希与变更检测（src/ow2_patch/diff.py）

- 结构化后 hash 走 sections bag（chrome 天然免疫）；`clean_legacy_text` 与 `is_cosmetic_diff` raw_text 分支保留（供仍降级的补丁与迁移期对比）。

### D4 web 与数据（管道主体无需改）

- `initPatch`/`heroBlock` 对 sections 自动生效（卡片/TOC/头像/图标/列表/加粗）；`renderRawText` 保留为兜底。
- 图标走本地 slug 库（legacy 无官方图标；OW1 英雄/技能图标已齐，缺失 onerror 隐藏）。
- `regenerate_all` 自动重建 heroes/*.json（2016-2020 时间线条目）、entries_index、pairing、ability_map（EN-only 支持已预留）。

### D5 scoped 迁移（tools/migrate_legacy.py）

- 仅扫 en 2016-05..2020-01（45 个月份）→ `run_pipeline(force_rewrite=True)`（不写 changelog/不通知）→ 内置 regenerate_all。
- 现代补丁解析路径未动，不重扫（字节不变）。

## [S3] Out of Scope

- CN legacy（CN 站 2025-02 起归档，无 legacy）。
- legacy 官方图标（旧页无图标资源，走本地库）。
- 逐补丁人工校对（启发式+fallback，用户已接受）。

## Tasks

- [ ] T24: 特性文档 — acceptance: 本文档含设计与任务（covers: 全部）
- [ ] T25: names.py `is_known_hero` — acceptance: 已知英雄（含别名）True、未知名 False（covers: D2；depends: T24）
- [ ] T26: parse.py legacy 结构化解析 — acceptance: 2016-07-19 fixture 解析出 sections（hero_update 含 Ana/McCree 等英雄、ability/general/dev），raw_text=None（covers: D1 D3；depends: T25）
- [ ] T27: tools/migrate_legacy.py — acceptance: 仅扫 en 2016-05..2020-01 并 force-rewrite（covers: D5；depends: T26）
- [ ] T28: 测试更新（变体 fixture、hash/pipeline/entries、smoke/layout_check）— acceptance: pytest 与 smoke/layout_check 全过（covers: D1 D3 D4）
- [ ] T29: scoped 迁移 + rebuild 收敛 + 全量验证 — acceptance: 103 个 legacy JSON 结构化、重扫零事件、现代补丁字节不变（covers: D5；depends: T27）
- [ ] T30: 独立 review 与规格定稿 — acceptance: review 无 critical，status: delivered（covers: 全部；depends: T29）
