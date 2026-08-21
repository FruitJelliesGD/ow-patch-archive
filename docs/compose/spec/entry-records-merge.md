---
feature: entry-records-merge
status: in-progress
updated: 2026-08-22
branch: feat/entry-records-merge
commits: <base-sha>..<head-sha> # filled at delivery
---

# 词条修改记录中英文合并显示（迭代十）

## Report

## [S1] Problem

词条详情页（entry.html）与英雄轨迹页（hero.html）的修改记录列表中，同一改动的**中英文记录分两行显示**：配对补丁（patches_index.json 的 `p-*` 含 `patch_id_en`+`patch_id_cn`）在 `data/heroes/{slug}.json` 时间线里产生两条单站点记录（EN 记录 `text_en` / CN 记录 `text_cn`，日期常差 1 天，实证 `cn-2025-03-26-1` ↔ `en-2025-03-25-1`），用户需在同一改动上看到两条独立行。目标：**合并为一行、中文优先**（中文文本为主、英文作副文本），仅显示中文记录日期。

## [S2] Design

### D1.1 配对映射

`buildPairMap(patches)`：patches_index.patches → `site patch id → {id: p-*逻辑id, other: 对端site id, title_cn, title_en}`（仅含双端 id 的 55 个配对；287 个未配对 EN-only 不产生映射）。

### D1.2 记录合并（kind + 计数门控 + 数值指纹）

`mergeEntryRecords(records, pairMap)` → 行数组，每行 `{m: 合成记录, en: en记录|null}`：

- 按（逻辑配对, entry key）分组，组内 en/cn 记录保持时间线顺序。
- **合并条件**（实证修正——纯位置合并对 `other::` 有 23% 错配，绝不可用）：
  1. `len(en) == len(cn) > 0`；
  2. kind ∈ {ability, weapon, perk} **或** 双方各 1 条（任意 kind 的 1 对 1）；
  3. **数值指纹一致性**：`en[i]` 与 `cn[i]` 文本若双方都含数字且数字交集为空 → 拒绝合并。
- 位置配对依据：双站由同一解析器确定性产出同一改动序列（ability 计数错配 3/366、perk 0/283；`other` 85/279 已由门控排除）。
- 合成记录 `m = {...cnRecord, text_en: en.text_en, lines_en: en.lines_en, url_en: en.url, en_patch: en.patch, patch_title: pair.title_cn || cn.patch_title}`（cn 为主，缺失时 en 兜底）。
- 门控外（未配对 / 计数不等 / kind 不符 / 指纹冲突）→ 原样单行。
- **已知限制**：同改动被双站分类进不同词条（实证 soldier-76 2026-06-16 EN `attr::base_stat` vs CN `weapon::heavy-pulse-rifle`）→ 各自单行，词条层不可修复，不在本迭代范围。

### D1.3 entryNode 扩展

合并检测用记录标记 `e.en_patch`（hero.html 的 initHero 不传 opts）：

- head：`e.en_patch` 存在时渲染**中文站 + 英文站双徽标**；日期 = `e.date`（仅中文日期）；patch 链接 = `patch.html?id=<p-*>&lang=cn`；官方事后编辑徽标 = 两个 site patch edits **并集去重**（调用处计算传入 opts.edits）。
- body：既有双语文案路径（text_cn 主 + text_en `.en-text` 副；perk 同理 lines_cn 主 + lines_en 副 + status）；追加 EN 侧「英文原文 ↗」链接（`e.url_en`，与主「查看官方补丁原文 ↗」区分）。
- 未合并行渲染完全不变。

### D1.4 initEntry

已有 patches_index → buildPairMap；records 先 merge 再渲染（entryNode 传 edits 并集）；meta「N 条更改记录」= 合并后行数。

### D1.5 initHero

**新增**懒加载 patches_index.json（失败降级为不合并，保持单行）；buildPairMap + merge；保持 hero.html 现状无 patch 链接；「共 N 条记录」= 合并后行数。

### D1.6 计数语义

两页计数改为合并后行数。词条卡片（entries_index `e.count`）为数据层原始计数保持不动——与合并计数的差异为已知不一致（数据层改动不在本迭代）。

### D1.7 CSS

`.en-text` 目前无样式规则（双语文案分支从未触发）——合并首次激活该分支，补 `color: var(--muted)` 次级语言样式。

## [S3] Out of Scope

- 数据层合并（build_hero_files 生成双语合并时间线）——改动 entries_index/heroes 全链路与官方编辑 join，不做。
- 词条卡片计数（entries_index `e.count`）与合并计数对齐。
- 跨分类（EN `attr::` vs CN `weapon::`）改动的合并。

## Tasks

- [x] T1: 特性文档 — acceptance: 本文档含设计与任务（covers: 全部）
- [x] T2: buildPairMap + mergeEntryRecords — acceptance: 门控规则生效（ability/weapon/perk 等计数合并、other 仅 1 对 1、指纹冲突拒绝），单测可验证（covers: D1.1 D1.2）
- [x] T3: entryNode 合并行 + .en-text 样式 — acceptance: 合并行双徽标/仅中文日期/EN 原文链接/edits 并集，单行无回归（covers: D1.3 D1.7；depends: T2）
- [x] T4: initEntry/initHero 接入 + 计数语义 — acceptance: 两页合并显示、hero.html 懒加载降级安全（covers: D1.4 D1.5 D1.6；depends: T3）
- [x] T5: smoke 断言 + 全量验证 — acceptance: smoke ALL OK、serve 预览词条/英雄页合并正确（covers: 全部；depends: T4）
- [ ] T6: 独立 review 与规格定稿 — acceptance: review 无 critical、status: delivered（covers: 全部；depends: T5）
