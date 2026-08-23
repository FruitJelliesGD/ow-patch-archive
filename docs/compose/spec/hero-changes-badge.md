---
feature: hero-changes-badge
status: delivered
updated: 2026-08-22
branch: feat/hero-changes-badge
commits: 96e7675..81132c2
---

# 「英雄改动」徽章 + 筛选 chip（按时间预览页）

## Report

**What was built** — 按时间预览页（index.html）补丁条目新增**「英雄改动」徽章**，并配套新增同名**筛选 chip**。后端 `build_patches_index` 为每条目新增结构化布尔字段 `has_hero_changes`（与 mode 无关）：任一侧补丁 JSON 存在 ≥1 个 balance hero 块（复用 `_is_balance_hero`，排除 Stadium 面具外观块与物品块）且携带实际改动内容（命名的 ability 带 changes / 任意 perk / 有文本的 general / 有行的 stadium item）——与 `build_hero_files` 向标准英雄历史产记录的口径完全一致，自动排除 `en-2022-01-06-1` 型空内容英雄块。前端徽章与 chip 统一按 `mode === "standard" && has_hero_changes` 门控：非常规模式补丁（愚人节/PTR/实验/试玩/社区创造/QP 黑客/公告）即使含英雄块（如 `p-2026-04-01-1` 愚人节 50 个英雄块）也不标注。`hero_changes` 键加入 app.js `CATEGORY_LABEL`（`setFilter`/`?cat=` 白名单随之生效），chip 在 CATEGORY_ORDER chips 之后追加，过滤谓词与徽章同口径。

- **数据实证**（343 条目）：徽章面 **181**（standard+flag）；10 个非常规补丁 flag=true（证明 mode 门控必要）；锚点全符合——`p-2026-08-11-1`（标准，32 块）true、`p-2026-08-19-1`（标准，无英雄）false、`en-2022-10-04-1`（公告）false、`en-2022-01-06-1`（空内容块）false。
- **review 一轮**：general-2 全部验收标准 MET、0 critical；3 项非关键中采纳 1（fixture 补 named-ability-with-changes 正例），驳回 2（smoke `children[4]` 索引——DOM shim 的 getElementById 是注册表、createElement 元素取不到，属既有约束；`_general_text` 无类型守卫——与生产 `build_hero_files` 逐字同构，None general 属不可能场景且生产同样失败）。

**Verification** — `pytest -q` → 244 passed（基线 242 +2 新增，warnings 为既有基线）；`node tools/_smoke_web.js` → ALL WEB ASSERTIONS OK（indexHasHeroChangesBadge / indexSpecialNoHeroBadge / indexAnnouncementNoHeroBadge / chipCount=16 / heroFilteredCount=181 且全带徽章）；`python tools/rebuild.py --data data` 双跑字节幂等，`git diff` 数据侧仅 `data/patches_index.json`（其余 858 个数据文件零变化）；`npx --yes -p playwright node tools/_layout_check.js` → ALL LAYOUT ASSERTIONS OK（12/12）；真实浏览器端到端（serve + playwright）：徽章 181 个、`#ffd54f` 金色渲染、chip 点击过滤 181 条全部带徽章。

**Journey log** — ① 工作区陷阱：会话 cwd 切到 worktree 后，edit/write 用主仓库绝对路径会把改动写进 main checkout——必须先 `git restore` 主库误改文件再对 worktree 路径重放（本特性一次踩坑，已清理干净）。② editable install 指向主仓库 src：worktree 内跑 pytest 必须 `PYTHONPATH=<worktree>/src`，否则 import 的是 main 的代码（fixture 测试首跑因此假失败）。③ 「英雄改动」语义不能只看 hero 块存在：`en-2022-01-06-1`（标准、6 块但 changes 全空）会被误标——flag 必须与 `build_hero_files` 产记录口径一致（内容感知），实测 182 块存在 vs 181 内容判定，仅此一例不同。④ `hero_changes` 键必须进 CATEGORY_LABEL：`setFilter`/`?cat=` 经 `CATEGORY_LABEL[k]` 白名单，缺键会被静默丢弃（review 前自查发现，勿只加 chip 渲染）。⑤ 常规补丁内嵌 QP 黑客内容块（如 `p-2026-01-08-1`）保持 standard mode、其英雄数据本就在标准历史 → 徽章显示，与英雄历史口径一致（系统既有约定）。

## [S1] Problem

按时间预览页（index.html）的补丁条目目前只有站点/模式/内容类别徽章（`sites`/`mode`/`categories`），无法一眼看出**哪些补丁包含常规模式下的英雄平衡改动**。用户希望新增「英雄改动」徽章，且**只对包含常规模式（standard）英雄平衡改动的补丁标注**——非常规模式补丁（愚人节/PTR/实验模式/英雄试玩/社区创造/QP 黑客入侵/公告）即使含英雄块也不标注。同时希望该信号可像内容类别一样作为**筛选 chip** 使用。

## [S2] Design

### D1 语义：`has_hero_changes`（结构化事实）+ 前端 mode 门控

「常规模式下的英雄平衡改动」的口径 = 该补丁会向标准英雄改动历史（`data/heroes/*.json` 中 mode=standard 的记录）贡献 ≥1 条记录。拆成两层，职责分离：

- **后端字段 `has_hero_changes: bool`（与 mode 无关的结构化事实）**：任一侧（EN∪CN）补丁 JSON 的 `sections[].heroes[]` 中存在 ≥1 个 **balance hero 块** 且该块**携带实际改动内容**：
  - 块过滤复用 `pipeline.py` 的 `_is_balance_hero`（排除 Stadium 外观块 "xxx Mask"/"面具"、`NON_HERO_NAMES` 物品块 "Items"/"New Gadgets Added"/"General Items" 等）；
  - 内容判定与 `build_hero_files`（pipeline.py:374-445）产记录逻辑一致：命名的 ability 且 `changes` 非空；或任意 perk；或有文本的 general 条目（str 或 dict 的 text_en/text_cn）；或有非空行的 stadium item。
  - 目的：排除 `en-2022-01-06-1` 型补丁（标准模式、6 个 hero 块但全部 `changes: []` 且无 general/perk → 实际零改动，不标注）。
- **前端门控**：徽章仅在 `p.mode === "standard" && p.has_hero_changes` 时显示。非常规模式补丁（如 `p-2026-04-01-1` 愚人节，50 个 hero 块）`has_hero_changes=true` 但**不**显示徽章。

### D2 数据层（pairing.py `build_patches_index`）

- 新增私有助手 `_has_hero_changes(data) -> bool`：遍历 `sections[].heroes[]`，`_is_balance_hero` 过滤后按 D1 内容判定。
- 模块级 `from .pipeline import _is_balance_hero`（已验证无循环导入：pairing.py 顶层仅 stdlib 导入；pipeline.py 仅在 `regenerate_all` 函数内惰性 import pairing）。
- pair 条目：`"has_hero_changes": _has_hero_changes(en_data) or _has_hero_changes(cn_data)`；unpaired 条目用自身内容。
- **不**进入 `categories` 数组（categories 是短语扫描的内容标签；hero 改动是结构化信号，二者不混）。
- 迁移 = `tools/rebuild.py` 重生成；预期 diff 仅 `data/patches_index.json`（其余 858 个数据文件字节不变，已实证）。

### D3 前端（web/app.js）

- `CATEGORY_LABEL` 增 `hero_changes: "英雄改动"`（注释更新为 mirror of categories.py + 前端专用 hero_changes 键）。加入 CATEGORY_LABEL 是必须的：`setFilter`（l.365）与 `?cat=` 种子（l.384）经 `CATEGORY_LABEL[k]` 白名单校验，缺键会被静默丢弃。`CATEGORY_ORDER` 不变（chips 按它迭代，hero_changes 单独追加）。
- 新 `heroChangesBadge(p)`：`p.mode !== "standard" || !p.has_hero_changes` → `""`，否则 `<span class="badge hero-changes">英雄改动</span>`。
- `renderTimeBrowser` 条目 HTML：`modeBadge(p.mode)` 之后、`categoryBadges(p)` 之前插入 `heroChangesBadge(p)`。
- `filterMatches`：`k === "hero_changes" ? (p.mode === "standard" && p.has_hero_changes) : (p.mode === k || (p.categories||[]).includes(k))`（与徽章同口径）。
- `buildCategoryChips`：CATEGORY_ORDER 循环后，若 `patches.some(p => p.mode === "standard" && p.has_hero_changes)` 追加 chip（`dataset.cat="hero_changes"`，文本取 CATEGORY_LABEL，`?cat=hero_changes` 种子与 `setFilter(["hero_changes"])` 随之可用）。

### D4 样式（style.css）

`.badge.hero-changes` 新增配色（置于 `.badge.mode-owl` 后）：金色系（如 `background: rgba(255, 213, 79, 0.15); color: #ffd54f;`），与现有 event 橙 `#ffb74d`、new_map/section 绿 `#81c784`、new_hero 青 `#2ec5b0` 区分。

### D5 测试与 smoke

- `tests/test_pairing.py`：
  - tmp_path fixture（沿用 `_write_patch_json` + `PairResult` 模式，参照 test_pairing.py:149-179）：hero 块带 ability changes → true；无 hero 块 → false；仅 mask 块 → false；hero 块但空 changes/general（en-2022-01-06-1 形状）→ false；EN/CN 并集 → true；unpaired 按自身。
  - 真实数据不变量：`p-2026-08-11-1`（standard，32 个 balance 块）→ true；`p-2026-08-19-1`（standard，无 hero 块）→ false；`en-2022-10-04-1`（announcement，7 节 0 块）→ false；`en-2022-01-06-1`（空内容块）→ false；`p-2026-04-01-1`（april_fools）→ true（flag 真、mode 门控徽章）；全部条目字段为 bool；至少一个非常规补丁 flag=true（证明门控必要）。
- `tools/_smoke_web.js`（行级断言参照 l.68-79 的 href 定位模式）：
  - 正例：`p-2026-08-11-1` 条目含 `badge hero-changes` 与「英雄改动」；
  - 负例：`p-2026-04-01-1`（愚人节）、`en-2022-10-04-1`（公告）条目不含 `badge hero-changes`；
  - `chipCount` 15 → 16（chips 容器仍为 `#jump-bar` children[4]，追加顺序稳定）；
  - `setFilter(["hero_changes"])` 后条目数 >0 且 < indexPatches，且每个可见条目均含 `badge hero-changes`；`setFilter([])` 复位。

## [S3] Out of Scope

- patch.html 详情页标注（用户仅要求按时间预览页）。
- 后端 categories 表增加短语类目（hero 改动是结构化信号，非短语扫描）。
- 修改 `mode` 分类权威或 hero/entries/values 数据过滤。
- 非常规模式补丁的「英雄改动」标注（明确排除）。

## Tasks

- [x] T1: 特性文档 + worktree — acceptance: 本文档含设计与任务；`.worktrees/hero-changes-badge` 分支 `feat/hero-changes-badge`（covers: 全部）
- [x] T2: pairing.py `has_hero_changes` + pytest — acceptance: fixture 5 场景 + 真实数据不变量全绿（covers: D1 D2 D5；depends: T1）
- [x] T3: rebuild 重生成 — acceptance: 仅 patches_index.json 变化、双跑幂等（covers: D2；depends: T2）
- [x] T4: 前端徽章+chip+样式 — acceptance: 条目徽章（standard+flag）、chip 追加、过滤生效、`?cat=hero_changes` 种子（covers: D3 D4；depends: T3）
- [x] T5: smoke 断言 — acceptance: 正/负例徽章断言、chipCount=16、hero_changes 过滤断言全过（covers: D5；depends: T4）
- [x] T6: 全量验证 — acceptance: pytest/smoke/rebuild 幂等/layout 全绿（covers: 全部；depends: T5）
- [x] T7: 独立 review + 规格定稿 — acceptance: review 无 critical、status: delivered（covers: 全部；depends: T6）
