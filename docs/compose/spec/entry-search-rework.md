---
feature: entry-search-rework
status: delivered
updated: 2026-10-23
branch: main
commits: 未提交（本地变更）
---

# 词条检索重构：多词/别名匹配、分页、以及"卡片数字 = 页面行数"

## Report

**What was built** — 检索内核、结果列表、详情页与数据层四组改动：

1. **检索内核**（`web/app.js`）：新增 `foldSearch()`（NFKD 全角/重音归一 + 标点转空格）与每词条预计算文档（token 表 / 整串 / 紧凑名字段 / 混合脚本文本）；查询按词切分后**逐词 AND**，ASCII 词走「token 完全匹配 → 前缀 → 紧凑名前缀」，含 CJK 的词走子串；可搜字段增加维度标签（武器/技能/威能/英雄属性/英雄）与新旧英雄别名（McCree/麦克雷、Solider: 76、Junkerqueen…）；排序改为「名称完全匹配 → 名称前缀 → 英雄名命中 → 其他」，同级按合并后条数降序；命中词在名称与英雄行内高亮。
2. **结果列表**：默认视图分页（每页 60 条，底部「加载更多（还剩 N 条）」），筛选/查询变化重置页码；零结果渲染可操作空态（「没有匹配「q」的词条」+ 清空搜索 / 查看全部词条）；`?q=` 保留用户输入的大小写、`?dim=` 只接受合法维度（非法值丢弃并回写 URL）；卡片链接携带 `q`/`dim`，详情页的「← 词条检索」和顶部导航据此返回同一结果集。
3. **详情/英雄页**：`initEntry`/`initHero` 读取 `entries_index.json` 作为**规范名来源**（卡片名、详情标题、英雄页分组标题一致；修复"卡片 重脉冲步枪、详情 脉冲步枪"的 2016 旧名问题），详情页显示别名（`variants` 去掉规范名后去重），kind 徽章按维度标注（武器改动/属性改动，不再是武器的「技能改动」），记录数取索引的合并后条数。
4. **数据层**（`src/ow2_patch/entries.py`）：新增 `changes` 字段 = 详情页实际渲染的合并行数，逐行移植 `web/app.js mergeEntryRecords()`（同分组键 = 逻辑补丁 + `entryKey`；门限 = 两侧条数相等且（ability/weapon/perk 或一对一）；数值指纹 veto）；配对表从 `patches_index.json` 读取（与前端 `buildPairMap` 同源），缺失时退化为不合并。`count` 语义不变，`schema_version` 仍为 1。

**Verification** —
- `python -m pytest -q` → **305 passed**（+5：合并计数四例 + 真实数据不变量，含 `sombra::ability::hotfix` 24→12、`soldier-76::weapon::heavy-pulse-rifle` 18→17）
- `node tools/_smoke_web.js` → **ALL WEB ASSERTIONS OK**：新增 17 条检索探针、分页（60→120→重置）、零结果空态、`?q` 大小写、返回链接、**全部 949 条词条的跨语言一致性**（JS 现算合并行数 == 索引 `changes`）
- 一次性 Playwright 脚本（未提交，真实浏览器）：22 项全 PASS —— 首屏 60 卡、加载更多 120、`soldier 76`→22 条、`dva`→D.Va 置顶且不再返回秩序之光「高级传送」、`ana grenade`→1 条、`soldier76`/`武器`/`麦克雷` 命中、零结果可操作、`?dim=bogus` 回落「全部」、URL 保留大小写、卡片链接带 `q`、详情标题 == 卡片名、补丁行数 == 卡片条数（17）、别名行可见（`Widow’s Kiss`）、0 console error / 0 4xx
- `npx -p playwright node tools/_layout_check.js` → 12/12 PASS
- `python tools/rebuild.py --data data` 连跑两遍 → 第二次无改动；`git diff --stat` 仅 `data/entries_index.json` 949 行插入（每条 +1 个 `changes` 字段）

**Journey log** —
① 逐字复刻 JS 合并逻辑时踩到 `entryKey` 的 null 语义差异：JS 对非索引维度返回 `"other::"`（会参与合并），Python `entry_key()` 返回 `None`（被索引丢弃）。第一版直接复用 `entry_key` 导致 34 条 hero 词条的 `changes` 多 2，smoke 的跨语言一致性断言立刻抓出来（`js=269 index=271`）——遂新增 `_js_entry_key()` 专供合并使用。
② 词条数的口径有三种候选：原始记录（两侧各算，24）、逻辑补丁数（1）、合并行数（12）。只有合并行数等于详情页实际行数，"卡片 = 页面"才成立；逻辑补丁数会把"一个补丁改 12 处"压成 1，反而失真。
③ "dva" 误命中秩序之光「高级传送」的根因是 `ad**van**ced` 里的 `dva` 子串：修法不是禁掉子串，而是把**紧凑名匹配限定为前缀**（`dva` 是 `d.va` 的前缀，却不是 `advanced` 的前缀）。
④ 中文没有空格，ASCII 的 token 规则会让「步枪」查不到「重脉冲步枪」→ CJK 查询单独走子串；反过来「76」要能命中「士兵76」，于是把含 CJK 的字段单独存一份供 ASCII token 子串匹配（避免把拉丁字段也卷进来再次引入 `dva`→`advanced`）。
⑤ 一次 PowerShell `Get-Content | Set-Content` 往返把 `tools/_smoke_web.js` 的中文全部毁掉（默认编码 GBK 读 UTF-8），只能 `git checkout HEAD` 恢复后重放两轮改动 —— 教训：改仓库文件只用编辑工具，批处理只用 py/node。

## [S1] Problem

词条检索可用但不可信，实测缺陷分四类：

1. **匹配**：标点/空格/重音/全角导致漏检（`soldier 76`、`soldier76`、`dmon`、`junkerqueen`、`wreckingball`、`bob` 全 0 命中；`dva` 只命中秩序之光的「高级传送」而 D.Va 本人 0 命中）；无多词 AND（`ana grenade`、`士兵76 脉冲步枪` 0 命中）；维度标签不可搜（`武器` 0 命中，`技能` 只命中「终极技能消耗」）；旧名不可搜（`麦克雷`/`McCree` 0 命中）。
2. **数字**：卡片 `count` 把 EN/CN 两侧各算一条，详情页按 `mergeEntryRecords` 合并 → 455/949 条不一致（`sombra::ability::hotfix` 卡片 24 / 详情 12；`hero::ana` 283 vs 合并后）。
3. **标题**：详情页与英雄页分组标题取**最早**记录的名字 → 436/949 条与卡片不一致（`重脉冲步枪 / Heavy Pulse Rifle` → `脉冲步枪`）；kind 徽章把武器标成「技能改动」。
4. **交互**：默认渲染全部 949 张卡片（8027 DOM 节点 / 43454px / 每次输入约 370ms）；零结果无提示无出口；`?dim=bogus` 无 chip 高亮且 0 结果；搜索状态在「列表 → 详情 → 返回」丢失；`?q` 被小写化。

## [S2] Design

### D1 检索内核（`web/app.js`）

- `foldSearch(v)`：`NFKD → toLowerCase → 去 \u0300-\u036f → [^\p{L}\p{N}] 转空格 → trim`；`compactSearch` 去空格。
- `buildEntrySearchDoc(entry)` 预计算：`_tokens`（全部字段 + 维度标签 + 英雄别名）、`_text`（整串，CJK 子串）、`_nameCompact`/`_heroCompact`/`_compactAll`（紧凑名前缀）、`_cjkText`（仅含 CJK 的字段，供 ASCII token 的混合脚本子串匹配）。
- `entryMatches(doc, tokens)`：每个 token 必须命中；CJK token → `_text.includes`；ASCII token → `tokenHits(_tokens, _compactAll)` 或 `_cjkText.includes`。
- `entryRank(doc, queryText, tokens)`：0 紧凑名完全相等 → 1 紧凑名前缀（长度 ≥2）→ 2 全部 token 命中英雄名 → 3 其他。
- 排序：`rank, changes desc, name(localeCompare zh)`。
- `highlightTokens(text, tokens)`：首个命中的 token 包 `<mark>`（分段 esc）。
- `HERO_SEARCH_ALIASES`：cassidy→McCree/麦克雷，soldier-76→Solider: 76/Soldier:76，junker-queen→Junkerqueen，illari→Iliari，d-va→DVa/DVA，d-mon→DMon，wrecking-ball→WreckingBall，lifeweaver→LifeWeaver。

### D2 列表交互（`web/app.js` + `entries.html` + `style.css`）

- `ENTRY_PAGE_SIZE = 60`；`entrySearchState = { q, dim, limit }`；`applyEntryFilter()`（筛选 + 排序 + 重置 limit + 同步 URL）、`renderEntryResults()`（渲染当前页 + `dataset.shown` + 底部状态）、`showMoreEntries()`（limit += 60 后只重渲染）。
- `#entry-status`：0 条 → `entryEmptyState()`（消息 + 清空搜索 + 查看全部词条）；未到底 → 「加载更多（还剩 N 条）」。
- URL：`syncURLState({ q: 原始输入, dim })`；初始化时 `ENTRY_DIM_ORDER.includes(dim)` 才接受，否则丢弃并回写。
- 卡片链接 `entryHref()` 追加 `q`/`dim`；`absorbEntrySearchParams()` + `applyEntriesNav()` 让详情/英雄页的 `#back-entries`、`#nav-entries` 指回同一结果集。

### D3 规范名（`web/app.js`）

- `entryDisplayName(entry)`（索引条目名，中文与英文相同时只显示一个）、`entryAliases(entry)`（variants 去规范名去重）、`kindLabel(kind, dimension)`。
- `initEntry` 增加 `entries_index.json` 依赖（421KB / 44KB gzip，失败时退回最新记录名）；英雄概览的条数取索引 `changes`；详情 meta 用 `rows.length`（跟随「包含非常规模式」开关）。
- `initHero` 构建 `key → 规范名` 表用于分组标题，失败时退回记录名。

### D4 数据（`src/ow2_patch/entries.py`）

- `_load_pair_map(data_dir)`：`patches_index.json` → `patch_id → 逻辑 id`（缺失 → `{}`）。
- `_js_entry_key(record)`：app.js `entryKey()` 的**非 null** 镜像（`other::` 也参与合并）。
- `merged_change_count(records, pair_map)`：逐行移植 `mergeEntryRecords()`。
- 每个条目输出 `changes`；`count` 不变。

### D5 测试

- `tests/test_entries.py`：`merged_change_count` 四例（共享数字合并 / 数字 veto / 无配对退化 / 两侧条数不等）；带 `patches_index.json` 的合成索引断言 `count=2 & changes=1`；真实数据不变量（`1 ≤ changes ≤ count`、hotfix 24→12、heavy-pulse-rifle 18→17）。
- `tools/_smoke_web.js`：17 条检索探针、分页三段、零结果空态、`?q` 大小写、返回链接、**全量跨语言一致性**（复用 app.js 的 `mergeEntryRecords` 现算并比对每条 `changes`）。

## [S3] Out of Scope

- 不把补丁正文/记录文本纳入检索（索引不携带正文）；不做拼音、繁简转换、模糊拼写纠错。
- 不改 `count` 字段语义（新增 `changes` 而非重定义），`schema_version` 保持 1。
- 不做服务端搜索、不做「按角色（重装/输出/支援）」检索（避免一搜"支援"刷屏）。
- 已知数据治理问题（本次不修）：`magentic-grenade` 与 `magnetic-grenade` 是源站拼写分裂产生的近似重复词条；173 条能力仅有英文名（CN 站 2025-02 才开始归档）。标准修法是补 `data/names.json` 后 `tools/rebuild.py`，与本次代码重构分开。

## Tasks

- [x] T1: `entries.py` 新增 `changes` + `_js_entry_key` + `merged_change_count` —— acceptance: 合成/真实数据单测通过；rebuild 只改 `entries_index.json`（covers: D4, D5）
- [x] T2: 检索内核（fold/token AND/紧凑前缀/排序/别名/维度标签/高亮） —— acceptance: 17 条探针全绿（covers: D1, D5）
- [x] T3: 分页 + 空态 + URL 归一 + 状态延续 —— acceptance: 60→120→重置；`?dim=bogus` 回落；返回链接带 `q`（covers: D2, D5）
- [x] T4: 详情/英雄页规范名 + 别名 + kind 修正 —— acceptance: 详情标题 == 卡片名；卡片条数 == 页面行数（covers: D3, D5）
- [x] T5: 全量验证（pytest 305 / smoke / layout 12 / 真实浏览器 22 项） + spec/README —— acceptance: 全绿、rebuild 幂等（covers: D1-D5）
