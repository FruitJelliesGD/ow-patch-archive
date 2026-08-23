---
feature: category-recognition
status: in-progress
updated: 2026-08-22
branch: feat/category-recognition
commits: # filled at delivery
---

# 分类徽章识别重写：作用域化扫描 + 结构信号 + 手动标记

## Report

## [S1] Problem

时间浏览页的内容分类徽章（categories.py 短语扫描补丁全内容）误判率高：season 76 标注仅 24 正例（52 误判：街机赛季、Bug 修复提及、开发注、奖励清单等）；new_hero 37 标注 24 正例（13 误判：平衡改动、角斗领域物品、皮肤等）；owl 误判率 ~60%（`\bOWL\b` 大小写不敏感命中 "Snow Owl Ana" 皮肤）；arcade ~25%（奖励模板文案）；event ~15%、new_map ~14%（Bug 修复/路线图/UI 标签引用）。用户要求优化识别方式，修复全部噪声类目；新赛季召回采用手动标记机制。

## [S2] Design

### D1 机制：每规则扫描作用域 + 守卫 + 结构信号 + 手动标记

`categories.py` 新增 `CATEGORY_SCOPES`（每规则作用域）、每规则守卫与 `categorize_patch(ctx)`；**`categorize_content(text)` 保持 WHOLE 语义不变**（test_categories.py 参数化用例与表完整性测试不破）。

- 作用域枚举：`WHOLE`（title+全内容，现状语义）/ `TITLE_SECTIONS`（title+section 标题+block 标题）/ `TITLE_FIRST`（title+首个非空 section 标题）。
- `PatchContext`：title、first_section、sections=[Section(title, heroes, block_titles)]、all_strings；由 pairing.py `_patch_categories` 从补丁 dict 构建，每侧调用 `categorize_patch`，条目 categories = EN∪CN（保 CATEGORY_ORDER 序）。
- **new_hero 守卫（仅 section 标题命中）**：该 section 有 ≥1 英雄且全部为 Stadium 内容（`stadium_items` 非空）或空壳（无 abilities/general/perks）则跳过——杀 `p-2025-12-09-1` "New Heroes Added"（角斗领域英雄物品区）；不作用于 block 标题（Baptiste "New Hero: Baptiste" 的 section 同为空壳，误杀会丢正例）。判别用 stadium_items/空壳内容，**不能用 `_is_balance_hero`**（该类 hero 块名字普通，如 Doomfist/Wuyang，会返回 True）。
- **season 守卫**：TITLE_FIRST 命中含 `continues|精彩继续` 则跳过（杀 `p-2025-09-16` "Season 18 continues" 及其 CN 对）。
- **new_hero 结构信号**（build_patches_index 内计算）：slug 的最早平衡记录日期 == 该补丁日期 且 日期 ≥ 2022-06-01 且 无更早补丁内容提及该英雄名（EN 名**词边界**匹配 `\bX\b` re.I——子串匹配误伤 adventure/dominated/shion；CN 名子串匹配）。已验证命中 10 个：ramattra/lifeweaver/illari/mauga/juno/hazard/freja/wuyang/anran/vendetta；JQ/Sojourn/Kiriko 被更早提及（en-2022-10-04）正确排除。
  - **幂等性要求**：最早记录日期与首次提及映射必须**从 `data/patches/{en,cn}/*.json` 补丁文件直接扫描计算**，不得读 `data/heroes/*.json`——regenerate_all 中 build_patches_index 先于 build_hero_files 运行，增量管道首轮（新英雄刚抓取）会读到陈旧 heroes 产物导致首轮漏标、次轮补标（不幂等）。
- **手动标记**：新建 `data/manual_categories.json`：`{index_id: [keys]}`，build_patches_index 加载并入集到 `categories`（文件缺失容忍）。用于 season 召回与 new_hero 特殊补录。

### D2 各分类最终规则（EN|CN，re.I；owl 的 OWL 用 `(?-i:\bOWL\b)`）

| key | 作用域 | 规则/守卫 |
|---|---|---|
| 6 模式类 + stadium + workshop | WHOLE | **原样不动**（模式类需 WHOLE：标注正文提及模式的常规标题补丁，如 p-2026-01-08-1；标签与 MODE_LABELS 一致约束不变） |
| season | TITLE_FIRST | `Season\s+(?:\d+|One\|Two\|...\|Ten)` / `第\d+赛季`；守卫 `continues\|精彩继续` |
| new_hero | TITLE_SECTIONS | 现有 `New (?:Support \|Tank \|Damage )?Hero(?:s)?(?! Option)` / `新英雄` + Stadium 守卫（section 标题级）+ 结构信号 |
| owl | TITLE_SECTIONS | `(?-i:\bOWL\b)\|Overwatch League` / `守望先锋联赛`（裸 `联赛` 删除） |
| arcade | TITLE_SECTIONS | `Arcade` / `街机` |
| event | TITLE_SECTIONS | 现有枚举（EN/CN 原样） |
| new_map | TITLE_SECTIONS | `New Maps?` / `新地图` |

### D3 验证后的计数（343 条全量 diff，实现时以实际为准）

| key | 前 → 后 | 后 TP/FP |
|---|---|---|
| season | 76 → 24 | 24/0 |
| new_hero | 37 → 28（26 规则 +2 override） | 28/0 |
| owl | 32 → 10 | 10/0 |
| arcade | 63 → 19 | 19/0 |
| event | 73 → 52 | 52/0 |
| new_map | 21 → 12 | 12/0 |
| 模式×6 / stadium / workshop | 不变 | 一致 |

### D4 手动标记清单（data/manual_categories.json）

| index_id | key | 依据 |
|---|---|---|
| en-2022-10-04-1 | season | S1/OW2 首发（正文 "Season One" 拼写；模式=announcement） |
| en-2023-08-10-1 | season | S6 发布（illari 首发；短语只在深层节） |
| en-2023-10-10-1 | season | S7 发布（只 "LIGHTING FOR SEASON 7" 深层节） |
| en-2023-12-05-1 | season | S8 发布（mauga；仅偶然 "Season 6" 正文） |
| en-2024-04-16-1 | season | S10 发布（venture 首发，全篇无 "Season 10"） |
| p-2025-12-09-1 | season | S20 发布（正文 "Season 20 patch"；首节 Winter Wonderland） |
| en-2024-03-28-1 | new_hero | Venture 限时试玩发布（desc 级 "Meet Venture…new Damage hero"） |
| p-2026-04-14-1 | new_hero | Sierra 发布（desc 级命中；结构信号因 CN +3d 不触发） |

（p-2025-08-26 曾候选 new_hero——驳回：命中为 "updated Stadium with new heroes"（角斗领域内容），属该删误判。）

### D5 已知召回损失（记录不处理，可后续 override 吸收）

event ~5（en-2017-01-24 等 body-only）、new_map ~6（Ayutthaya/Château Guillard/Shambali Monastery/Aatlis/Clash 地图/OW2 首发）、arcade ~6（Deathmatch/Bounty Hunter 等）。

## [S3] Out of Scope

- 6 个模式类与 stadium/workshop 的识别逻辑（行为不变）。
- 前端 web/app.js / style.css / smoke（chipCount 仍 16——14 类均有数据；event 过滤计数变化仍在断言区间；p-2026-01-08-1 quick_play_hacked 不变量不变）。
- 词条/英雄页数据（categories 不向下游供数）。
- event/new_map/arcade 的召回损失（记录于 D5）。

## Tasks

- [ ] T1: spec 文档 + worktree — acceptance: 本文档含设计与任务；`.worktrees/category-recognition` 分支 `feat/category-recognition`（covers: 全部）
- [ ] T2: categories.py 机制（scope/guard/ctx）— acceptance: test_categories.py 新旧用例全绿（covers: D1 D2；depends: T1）
- [ ] T3: pairing.py 集成 + manual_categories.json + 测试 — acceptance: 新增用例全绿（结构信号/override/union fixture 修复）（covers: D1 D2 D4；depends: T2）
- [ ] T4: rebuild 重生成 — acceptance: 仅 patches_index.json + manual_categories.json 变化；各 key 计数与 D3 一致；双跑幂等（covers: D3；depends: T3）
- [ ] T5: 全量验证 — acceptance: pytest/smoke/layout 全绿 + 真实浏览器抽查（covers: D3 D5；depends: T4）
- [ ] T6: 独立 review — acceptance: review 无 critical（covers: 全部；depends: T5）
- [ ] T7: 独立 review + 规格定稿 — acceptance: status: delivered、Report 填毕（covers: 全部；depends: T6）
