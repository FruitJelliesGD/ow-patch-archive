---
feature: content-categories
status: delivered
updated: 2026-08-22
branch: feat/content-categories
commits: 39d6bb7..d96be67
---

# 内容分类徽章 + 时间浏览页多选筛选（迭代十五）

## Report

**What was built** — 时间浏览页（index.html）新增**内容分类体系**：构建期遍历全部 398 个补丁文件（EN+CN）内容，按 14 个类别短语（模式 6：QP 黑客入侵/愚人节/实验模式/英雄试玩/PTR/社区创造；内容 8：活动/新赛季/新英雄/新地图/角斗领域/街机/自定义工坊/联赛）识别，`patches_index.json` 每条目新增 `categories` 数组（取代 `content_qp_hacked` 布尔字段）。补丁条目与详情页渲染类别徽章（与 mode 徽章去重），顶部时间跳转栏内新增**多选 chips 筛选**（OR 语义，「全部」默认，`?cat=a,b` 初始态，本地 state 重渲染）。**纯显示层**：mode 分类与 hero/entries/values 数据过滤零变化。

- **数据实证**（rebuild 后 343 条目）：14 类全部命中——qp_hacked 7 / april_fools 5 / experiment_6v6 3 / hero_trial 9 / ptr 3 / community_created 4 / event 73 / season 76 / new_hero 35 / new_map 21 / stadium 58 / arcade 63 / workshop 98 / owl 32；`p-2026-01-08-1`/`p-2026-07-30-1` categories 含 quick_play_hacked 且 mode 仍 standard（混合补丁常规数据保留）。
- **正则实证修正**：`New Hero(?:s)?` 误写（Hero+e+s? 不匹配 "New Hero"）；new_hero 需 `(?:Support |Tank |Damage )?`（各分支带尾随空格）才能命中 "new Support Hero Illari" 形态；`(?! Option)` 排除 "New Hero Option:" 设置项假阳性（2017/2023 数据实证）。
- **review 两轮**：general-3 两处 CRITICAL（pair 并集 dict.fromkeys 保 en 首现序非 CATEGORY_ORDER——4 条乱序；new_hero 正则漏角色修饰——en-2023-08-10-1/en-2024-07-19-1 漏判）→ 修复 d96be67；general-4 复审 0 critical。

**Verification** — `pytest -q` → 242 passed（206 基线 +36：test_categories 33 参数化+2 表完整性+标签一致、pairing 并集 tmp 单测）；`node tools/_smoke_web.js` → ALL WEB ASSERTIONS OK（chipCount=15、setFilter(['event'])→filteredCount=73 < 343、filterReset、indexCategoryBadge/patchCategoryBadge）；`python tools/rebuild.py` 双跑幂等；`git diff 39d6bb7..` 仅 data/patches_index.json + 代码/测试/smoke/style + spec，hero/entries 数据零 diff。

**Journey log** — ① 摸底统计 398 文件时 `json.dumps` 会含 JSON **键名**（`stadium_items` 键误计入 248），真实内容命中须走值遍历（实测 stadium 58）——数据实证前先定义"内容"口径。② 正则"New Heroes?" 实为 Hero+e+s?（"Heroe"），"New Hero" 不匹配——s? 前的 e 是陷阱；角色修饰 `(Support|Tank|Damage )?` 只有 Damage 带尾随空格，`Support`/`Tank` 后需空格。③ smoke shim 的 getElementById 是注册表查找，createElement 的 chips 容器取不到 → 断言走 #jump-bar children[4] 索引（与 jump-bar 控件同模式）。④ pair 并集保序不能靠 `dict.fromkeys(en+cn)`（en 首现序），须按 CATEGORY_ORDER 重建——交错用例（en=[season,stadium]+cn=[new_hero]）才能测出。⑤ 6 个模式类的 CATEGORY_LABELS 必须与 MODE_LABELS 逐字一致，否则去重徽章因来源不同显示不同文字。

## [S1] Problem

时间浏览页（index.html）只能按时间浏览全部补丁，无法按补丁**内容**区分。此前仅有标题规则驱动的模式徽章（`mode`）与单一 QP:H 内容徽章（`content_qp_hacked`）。用户希望像 QP:H 内容识别一样，**遍历全部补丁内容**识别出内容类别（活动/赛季/新英雄/新地图/角斗领域/街机/自定义/联赛 + 既有 6 种模式），补丁条目带类别徽章，并在顶部时间跳转栏旁按内容类别**多选筛选**补丁。要求：纯显示层——`mode` 分类与 hero/entries/values 数据过滤完全不变。

## [S2] Design

### D1 分类表与新模块 `src/ow2_patch/categories.py`

14 个内容类别（key / 中文标签 / 判定短语，EN+CN，re.I，扫描补丁全内容）。**模式 6 类的标签必须与 modes.py `MODE_LABELS` 逐字一致**（去重后同一类别不因来源显示不同文字）：

- `quick_play_hacked` 快速比赛：黑客入侵 —— 复用 modes.py `QP_HACKED_PHRASE`（`Quick Play:?\s+Hacked|快速比赛：黑客入侵`）
- `april_fools` 愚人节 —— `Really, Really, Really Balanced|Totally Normal|Underwatch` / `完全正常|守望后卫`
- `experiment_6v6` 实验模式 —— `6v6\s*Experiment` / `6v6\s*实验`
- `hero_trial` 英雄试玩 —— `Hero Trial` / `英雄试玩`
- `ptr` PTR 测试服 —— `\bPTR\b` / `PTR`
- `community_created` 社区创造模式 —— `Community Crafted` / `社区创造模式`
- `event` 活动 —— `Anniversary|Summer Games|Halloween|Winter Wonderland|Lunar New Year|Archives|Starwatch|Junkenstein` / `周年庆|夏季运动会|万圣节|冬境乐园|春节|农历新年|行动档案|星际守望|狂鼠复仇`（**必须是多事件枚举，禁用裸 `event`/`活动`** 防通用词误伤）
- `season` 新赛季 —— `Season\s+\d+` / `第\d+赛季|(?<!\d)\d+赛季`
- `new_hero` 新英雄 —— `New (?:Support |Tank |Damage )?Hero(?:s)?(?! Option)` / `新英雄`（`(?! Option)` 排除 "New Hero Option:" 设置项误伤）
- `new_map` 新地图 —— `New Maps?` / `新地图`
- `stadium` 角斗领域 —— `Stadium` / `角斗领域`（命中面宽 ~248，用户接受）
- `arcade` 街机 —— `Arcade` / `街机`
- `workshop` 自定义工坊 —— `Custom Game|Workshop` / `自定游戏|自定义游戏|工坊`
- `owl` 联赛 —— `\bOWL\b|Overwatch League` / `联赛|守望先锋联赛`（EN 必须限定短语，裸 `League` 过宽）

模块导出：`CATEGORY_ORDER`（14 key 有序列表，徽章/筛选/chips 排序依据）、`CATEGORY_LABELS`（zh 标签，注释 `# mirrored in web/app.js CATEGORY_LABEL`）、`CATEGORY_RULES`（`(key, en_re, cn_re)` 列表）。职责分离：modes.py 是分类权威（标题规则，驱动数据过滤）；categories.py 是叠加显示标签（内容短语，纯展示）。

### D2 数据层（pairing.py `build_patches_index`）

- 内容遍历 `_content_strings(data)`：title + sections 递归（含 blocks/heroes/description/dev）+ raw_text；**跳过 http:// 开头的字符串**（hero icon CDN URL 防误伤）；不遍历顶层 id/url/site。
- `_patch_categories(data) -> list[str]`：按 CATEGORY_ORDER 序返回 EN 或 CN 正则命中的 key。
- 条目字段：**删除** `content_qp_hacked`（功能被类别吸收）；**新增** `"categories": [...]`——恒存在数组（无命中 `[]`），pair = en ∪ cn（去重、保 CATEGORY_ORDER 序），unpaired 用自身。
- 删除 `_mentions_qp_hacked` walker 与 `mentions_qp_hacked` 函数（QP 降级为普通类别；`QP_HACKED_PHRASE` 保留供 categories.py 复用）。
- 迁移 = `tools/rebuild.py` 重生成；mode/pairing/hero/entries 零变化 → 预期 diff 仅 `data/patches_index.json`。

### D3 前端（web/app.js + index.html）

- `CATEGORY_LABEL` JS 镜像（注释 `// mirror of src/ow2_patch/categories.py CATEGORY_LABELS`，同 MODE_LABEL 惯例）。
- `categoryBadges(p)`：`(p.categories||[]).filter(k => k !== p.mode)` 每个 key 渲染 `<span class="badge mode mode-<key>">标签</span>`（复用 mode 徽章类与配色）；删除 `qpContentBadge`。
- 徽章链（时间浏览条目 + patch.html `patch-sites`）：`siteBadges + modeBadge + categoryBadges`。
- `buildCategoryChips(patches)`：initIndex 中 buildJumpBar 之后调用；`<div class="chips" id="cat-chips">` 追加为 `#jump-bar` **最后一个子元素**（children[1]/[2] 仍为年/月下拉，smoke 既有断言不受扰）；chips = 数据中出现的类别 key（全部条目 mode 值 ∪ categories 并集）+ 前导「全部」（默认 `.active`）。
- 筛选状态：`const selected = new Set()`；类别 chip 点击 toggle（空集 → 全部 active），「全部」清空；**仅本地 state，不写 URL**（smoke shim 无 history 全局；符合 hero 页 `?modes=all` 先例）。
- 筛选谓词：`selected.size === 0 || [...selected].some(k => p.mode === k || (p.categories||[]).includes(k))`（OR 语义）。
- 重构：initIndex 的分组+DOM 循环抽为 `renderTimeBrowser(patches, filterFn)`；chip 变化 `container.replaceChildren()` 后重渲染（年/月锚点 id 稳定，跳转条不重建）。
- 初始态：`?cat=a,b`（split `,`，忽略未知 key）seed 到 selected；暴露 `setFilter(keysArr)` / `getFilter()` 供 smoke 直调（与 chips 同语义）。

### D4 样式（style.css）

`.badge.mode-event/season/new_hero/new_map/stadium/arcade/workshop/owl` 8 条配色（仿现有 `.badge.mode-*`，置于 l.121 后）；`[id^="year-"]` scroll-margin-top 上调（sticky 跳转条因 chips 变高）。

### D5 测试与 smoke

- `tests/test_categories.py`：每类 EN/CN 正向 + 负向（裸 `event`/裸 `League` 不命中）；`CATEGORY_ORDER`/`CATEGORY_LABELS` 完整性（14 key）；模式 6 类标签与 `MODE_LABELS` 一致。
- `tests/test_modes.py`：移除 `mentions_qp_hacked` 用例（函数已删），标题分类用例保留。
- `tests/test_pairing.py`：`test_real_patches_index_qp_hacked_content_flag` 改为 categories 不变量——`p-2026-01-08-1`/`p-2026-07-30-1` categories 含 `quick_play_hacked` 且 mode 仍 standard；`p-2026-08-11-1` categories 含 `season`/`stadium`；全部条目有 `categories` 数组；全条目无 `content_qp_hacked` 键。新 tmp_path 单测：**须向 tmp 写入真实结构补丁 JSON**（`_load_patch` 读 `data_dir/patches/`，缺文件返回 `{}` 拿不到内容）——pair EN「Season 5」+ CN「新英雄」→ `categories == ["season","new_hero"]`（并集/去重/保序）。
- smoke：删除 `indexQpHackedContentBadge`/`patchQpHackedContentBadge` 断言与收集循环，p-2026-01-08-1 条目改断言类别徽章文本；保留 `indexHasQuickPlayHackedLabel`；新增 `chipCount`（= 14 + 1 = 15）、`setFilter(['event'])` 后条目数 < 343 且 > 0、`setFilter([])` 回 343。

## [S3] Out of Scope

- `mode` 分类逻辑与 hero/entries/values 数据过滤（纯显示层，分类权威不变）。
- entries.html / hero.html 的筛选（用户指定时间浏览页）。
- 筛选 URL 写回（仅初始态）、类别多语言开关。
- 修复类（Bug Fixes）/平衡类等无区分度类别（几乎每补丁都有）。

## Tasks

- [x] T1: 特性文档 — acceptance: 本文档含设计与任务（covers: 全部）
- [x] T2: categories.py 模块 — acceptance: CATEGORY_ORDER/LABELS/RULES 齐全、14 key、模式类标签与 MODE_LABELS 一致（covers: D1）
- [x] T3: pairing.py categories 字段 — acceptance: 条目含 categories 数组、无 content_qp_hacked、pair 并集保序（covers: D2；depends: T2）
- [x] T4: rebuild 重生成 — acceptance: 仅 patches_index.json 变化、双跑幂等（covers: D2；depends: T3）
- [x] T5: 前端徽章+筛选 — acceptance: 条目/详情页类别徽章、跳转栏内多选 chips、筛选生效、?cat= 初始态（covers: D3 D4；depends: T4）
- [x] T6: 测试与 smoke 重基线 — acceptance: pytest/smoke 全过（covers: D5；depends: T5）
- [x] T7: 独立 review + 规格定稿 — acceptance: review 无 critical、status: delivered（covers: 全部；depends: T6）
