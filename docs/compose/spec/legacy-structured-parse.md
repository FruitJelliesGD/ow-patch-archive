---
feature: legacy-structured-parse
status: delivered
updated: 2026-08-21
branch: feat/legacy-structured-parse
commits: 4af2c63..80c1684
---

# Legacy 补丁结构化解析

## Report

**What was built** — 133 个 OW1 旧补丁（EN 2016-05 → 2020-01）不再降级为整块 `raw_text`，而是由新的 `_parse_legacy_chunk` 结构化为与现代补丁相同的 Section/HeroUpdate/AbilityUpdate/GenericBlock 模型：章节卡片、英雄块（头像 + 技能图标 + 项目符号改动行 + 开发注）、目录侧边栏、内联加粗全部自动生效；英雄改动时间线与词条检索获得 2016-2020 完整历史（soldier-76 时间线从 2016-07-19 起，含数值提取）。解析器按标题元素（h1-h4）切分章节、`<strong>/<b>` 标记经 `is_known_hero`/`is_known_ability` 判定英雄块与类别块、处理三种技能名形态（嵌套 li / 2019 plain-p / 2016 裸 b）、并列嵌套 ul、两种开发注形态，样板段落与站点 chrome 不进入数据。跨年变体（2016-2020 五年标记漂移）经 5 个真实 fixture 覆盖。scoped 迁移 `tools/migrate_legacy.py` 仅重扫 45 个月份；现代补丁零改动。

**Verification** — `pytest -q` → 153 passed；`node tools/_smoke_web.js` → ALL WEB ASSERTIONS OK（legacy 页 hero-avatar/change-list/TOC 可见/bastion 图标）；`npx -p playwright node tools/_layout_check.js` → 8 项全过；legacy+modern 重扫 0 events；rebuild 收敛；保真校验（迁移前 raw_text 子弹行 vs 结构化数据逐行比对，103 补丁）→ 13 个名字变体/子技能名差异，**零真实内容丢失**（Jump Jets→Jump Jet、Storm Arrows→Storm Arrow 等均为能力名规范化）；0 个无图标 slug（names.json "Widow's Kiss" slug 修正 + 引号归一化）；45 个 legacy 技能图标文件缺失（这些技能在现代表达中从未出现，无图标 URL 可下——页面 onerror 优雅隐藏，属设计内降级）。

**Journey log** — ① 结构数据"重扫 0 events"只能证幂等、不能证内容保真：hash 建立在已缩减内容上；首轮 review 用"旧 raw_text 子弹行 vs 新结构化 bag"比对检出 2 个 critical（block 内 p/ul 交错覆盖、含嵌套 ul 的 li 自身文本丢失）与 ~489 行丢失，修复后归零——该比对方法应保留为正式校验。② legacy 标记五年漂移极大：章节标题 31 种形态（strong-p 只有 PATCH HIGHLIGHTS/PATCH INTRODUCTION 安全入词汇表，"General"/"Competitive Play" 兼作类别词必须排除）；英雄标记三形态（strong-p / 裸 `<b><a>` / 2019 plain-p）；技能名有并列嵌套 ul（2017-04-11 Wall Ride 双 ul 曾丢一行）。③ `NameResolver.hero()/ability()` 对未知名返回 auto-slug 而非 miss——解析期必须用 `is_known_hero`/`is_known_ability` 前置判定。④ worktree 中 pytest 必须 `PYTHONPATH=<worktree>/src`（editable 安装指向主仓库旧代码致假失败）。⑤ 子技能名丢弃规则收敛为"短 + 已知技能名"（is_known_ability），优先保内容、容忍少量名字噪音行（Heal Song 等泄漏为改动行）。

## [S1] Problem

103 个 OW1 旧补丁（EN 2016-05-27 → 2020-01-28）当前降级为整块 `raw_text`，补丁详情页显示为无结构的纯文本，与新补丁（章节卡片、英雄块、头像/技能图标、项目符号、目录侧栏）格式差距大。英雄改动时间线也因此缺失 2016-2020 全部历史。

## [S2] Design

### D1 legacy 解析器（src/ow2_patch/parse.py）

- 触发：`_split_sections` 为空且 chunk 含 `--legacy` 类（或 h1-h4 章节标题）→ `_parse_legacy_chunk(soup, site)`。
- 剥 `.PatchNotesTop` / `.PatchNotesPagination` chrome；首个标题（h1/h2/h3）为 patch.title。
- 按标题元素切分 section：h1-h4 标题；strong-only `<p>`/`<b>` 仅当文本 ∈ 安全章节标记集（PATCH HIGHLIGHTS / PATCH INTRODUCTION——"General"、"Competitive Play" 等兼作类别词已排除）才开启新章节。
- section 内逐元素：`is_dev`（两种 em 形态：`<strong><em>Developer Comments:</em></strong><em>…</em>` 与单 em `Developer Comment:`）→ 挂最近 hero/block；strong-only p 且 `is_known_hero` → HeroUpdate(name_en)；strong-only p 未命中 → GenericBlock(title)；裸 `<b>`（2016 格式）同 strong-p 处理；`<ul>` → 有 hero 走 `parse_hero_list`，有 block 追加 `_list_lines(ul)` 并同步进 block_paras（防后到 `<p>` 覆盖），否则并入 description；plain p 且 hero 且后随 ul（2019 形态）→ AbilityUpdate；其余 p → description 或 block body。
- `parse_hero_list(ul, hero)`：顶层 li 有嵌套 ul（可多个并列）→ AbilityUpdate；无嵌套 → hero.general 行；改动行走 `_extract_numbers`。
- 嵌套 li 自身文本处理：短（<40 字符、无数字、无句点）**且** `is_known_ability` 命中的子技能名丢弃（其叶子改动并入父技能），其余一律保留为改动行（含自身子列表的改动行不丢失）。
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

- [x] T24: 特性文档 — acceptance: 本文档含设计与任务（covers: 全部）
- [x] T25: names.py `is_known_hero` — acceptance: 已知英雄（含别名）True、未知名 False（covers: D2；depends: T24）
- [x] T26: parse.py legacy 结构化解析 — acceptance: 2016-07-19 fixture 解析出 sections（hero_update 含 Ana/McCree 等英雄、ability/general/dev），raw_text=None（covers: D1 D3；depends: T25）
- [x] T27: tools/migrate_legacy.py — acceptance: 仅扫 en 2016-05..2020-01 并 force-rewrite（covers: D5；depends: T26）
- [x] T28: 测试更新（变体 fixture、hash/pipeline/entries、smoke/layout_check）— acceptance: pytest 与 smoke/layout_check 全过（covers: D1 D3 D4）
- [x] T29: scoped 迁移 + rebuild 收敛 + 全量验证 — acceptance: 103 个 legacy JSON 结构化、重扫零事件、现代补丁字节不变（covers: D5；depends: T27）
- [x] T30: 独立 review 与规格定稿 — acceptance: review 无 critical，status: delivered（covers: 全部；depends: T29）
