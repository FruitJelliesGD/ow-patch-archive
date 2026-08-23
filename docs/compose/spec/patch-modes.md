---
feature: patch-modes
status: delivered
updated: 2026-08-22
branch: feat/patch-modes
commits: 0965448..c4f96f7
---

# 常规/非常规模式补丁区分（迭代十一）

## Report

**What was built** — 区分常规与非常规模式补丁（快速比赛：黑客入侵 Quick Play: Hacked、社区创造模式 Community Crafted、愚人节、6v6 实验、英雄试玩、PTR、公告），非常规数据**不再干扰常规历史**：英雄轨迹/词条/数值轨迹默认只显示常规、可切换查看非常规；首页时间浏览与补丁详情页列出全部补丁并带模式徽标。

- **标题规则 + section 信号**（新模块 `modes.py`）：标题关键词（含 CN 愚人节 `完全正常`）→ 各模式；默认 standard；大小写变体（`OVERWATCH PATCH NOTES`）不误伤；**standard 标题但含官方 section 标记 `Community Crafted|社区创造模式` → `community_created`**（标题常规的社区创造补丁 p-2026-06-30-1/p-2026-07-01-1/en-2024-06-20-1 经此识别，非手工清单）。
- **数据层**：mode 唯一权威 = patches_index **pair 级**（任一侧非 standard 即非 standard，en 优先，再 section 信号）——`cn-2025-04-01-1`（中文标题 144 条记录）经 pair 兜底判为 april_fools；build_hero_files 反查 patch_id→mode 给每条时间线记录打标（**全部记录保留**供切换），**values 只喂常规记录**；entries_index 常规口径。实测：342/342 索引条目、10,788/10,788 时间线记录全部带 mode；**standard 9,540 + special 1,248**（community_created 613、april_fools 418 含 CN 144、experiment_6v6 113、hero_trial 104；quick_play_hacked/ptr/announcement 无 hero 结构 0 条）；entries 987→921。
- **前端**：hero.html/entry.html 默认 standard-only + 「包含非常规模式」切换（`?modes=all` 初始态或 checkbox 本地 re-render；过滤在 mergeEntryRecords 之前；hero-overview meta 随视图）；index.html 补丁条目与 patch.html 详情 header 显示模式徽标（`.badge.mode-*`）。
- **迁移**：仅 `tools/rebuild.py` 重生成（无解析/hash 变更）。

**Verification** — `pytest -q` → 187 passed（+21：modes 参数化用例、patch_mode_with_sections（Community Crafted/社区创造模式 命中与标题优先）、pairing pair 级 mode + real invariants（p-2026-06-30-1 community_created）、hero 记录 mode×2、entries 常规口径、parity 新契约）；`node tools/_smoke_web.js` → ALL WEB ASSERTIONS OK（新增 indexHasModeBadge、patchHasModeBadge（p-2025-04-01-1 愚人节）、heroDefaultNoSpecial、heroAllShowsSpecial、entryCards=921、entryMergedCount=17）；`npx --yes -p playwright node tools/_layout_check.js` → 12/12 PASS；rebuild 字节收敛（git diff 不变）；serve 探测 hero 默认/all、patch 均 200。独立审查：**0 critical**，2 项非关键（规格 D2 词条消失数 24→31 勘误、modes.py 死代码 `MODE_LABEL_EN`/`is_standard()` 已删）。交付后追加修正（用户反馈）：排除 7月1日社区创造模式 → section 信号识别 3 个 community_created 补丁（含 2024-06-20 同类），entries 956→921、standard 10,153→9,540。

**Journey log** — ① 标题分类必须用形态法而非宽泛关键词表（把月份 April 全误伤），且 `OVERWATCH PATCH NOTES` 大写变体是常规补丁不能误伤。② **CN 愚人节是设计代理抓到的关键坑**：`cn-2025-04-01-1` 中文标题 144 条记录 EN 关键词匹配不到，per-site 判定会判 standard 污染历史——mode 必须以 patches_index pair 级为唯一权威（build_hero_files 反查）。③ 非常规词条消失数实测 31 ≠ 设计预测 24（模拟少算）——实证优先。④ smoke DOM shim 无法触发 checkbox 事件（makeEl.addEventListener no-op）→ 切换初始态读 URL `?modes=all`（patch.html `?lang=` 先例）供可测，checkbox 仍本地 state。⑤ build_patches_index 单测写 tmp_path 时 unpaired 条目要读真实补丁文件会 FileNotFound——单测用纯 pairs PairResult 或读真实 data。⑥ **交付后追加修正**：用户反馈"排除7月1日的社区创造模式"——p-2026-06-30-1（EN 06-30 + CN 07-01）标题常规但 section 含官方「Community Crafted/社区创造模式」（51 英雄 291+ 条记录）——标题规则盲区，扩展 `patch_mode_with_sections`（section 信号），自动识别 3 个 community_created 补丁（含 2024-06-20 同类）；section 信号优于手工清单（同模式未来补丁自动排除）。

## [S1] Problem

英雄轨迹、词条、数值轨迹混入了非常规模式补丁（快速比赛：黑客入侵 Quick Play: Hacked、愚人节、6v6 实验、英雄试玩、PTR、公告）的英雄改动数据——实证非常规记录 **635/10,788（5.9%）**（EN 侧 491 + CN 愚人节 144），愚人节补丁一个就改 40+ 英雄。这些临时模式改动与常规天梯平衡无关，混入常规历史产生误导（如某英雄"伤害从 50 降至 45"实际来自愚人节补丁）。目标：区分常规/非常规补丁，非常规数据**不干扰常规历史**——英雄轨迹/词条/数值轨迹默认只显示常规、可切换查看非常规；首页时间浏览与补丁详情页列出全部补丁并带模式徽标。

## [S2] Design

### D1 标题规则 + section 信号（src/ow2_patch/modes.py）

`patch_mode(title) -> str` 按优先级正则匹配（re.I）：

- `Quick Play:? Hacked` → `quick_play_hacked`（快速比赛：黑客入侵）
- `Really, Really, Really Balanced|Totally Normal|完全正常` → `april_fools`（**CN 关键词兜底**——cn-2025-04-01-1 标题为「完全正常的"完全正常先锋"补丁说明」）
- `6v6 Experiment` → `experiment_6v6`
- `Hero Trial|英雄试玩` → `hero_trial`
- `\bPTR\b` → `ptr`
- `Unauthorized Peripheral|Welcome to Overwatch` → `announcement`
- 默认 `standard`

`patch_mode_with_sections(title, section_titles)`：标题规则优先；standard 标题但含官方 section 标记 **`Community Crafted|社区创造模式`** → `community_created`（社区创造模式）——标题常规的社区创造补丁（实证 p-2026-06-30-1、p-2026-07-01-1、en-2024-06-20-1）经此识别，非手工清单。

`MODE_LABELS`（py）+ 前端 JS 镜像：`{quick_play_hacked: 快速比赛：黑客入侵, april_fools: 愚人节, experiment_6v6: 实验模式, hero_trial: 英雄试玩, ptr: PTR 测试服, announcement: 公告, community_created: 社区创造模式}`。**已知局限**：未来新模式标题与 section 均无信号 → 默认 standard 漏判。

### D2 数据层（mode 以 patches_index pair 级为唯一权威）

- **pairing.py → patches_index**：每个条目加 `mode`——pair 取 en/cn **任一侧非 standard**（en 优先）；unpaired 用自身 title 判定；同时提供 **patch_id → mode**（pair 两侧同 mode，供 build_hero_files 反查——CN 愚人节经 pair 兜底判为 april_fools）。
- **build_hero_files**（pipeline.py）：读 patches_index 建 patch_id→mode 映射（缺省 `patch_mode(title)` 兜底）；每条时间线记录加 `"mode"`（**全部记录保留**供前端切换）；**values 只喂常规记录** `build_values([e for e in entries if e.mode == "standard"])`（数值轨迹默认常规）。
- **build_entries_index**（entries.py）：**常规口径**——只统计 `mode == "standard"` 记录（count/edited/first/last_date 基于常规）；非常规-only 词条从检索消失（常规口径的预期结果，entries 987→921：标准补丁外所有模式记录不贡献词条）。
- hash/解析层不动（mode 是派生数据）→ 迁移 = `tools/rebuild.py` 重生成，无需 force-rewrite。

### D3 前端

- **index.html**：补丁条目显示模式徽标（`p.mode !== "standard"` 时）。
- **patch.html**：header 显示模式徽标（`meta.mode`）。
- **hero.html**：默认只渲染 `mode === "standard"` 记录 + 「包含非常规模式」切换控件（本地 state，点击 re-render；记录过滤在 mergeEntryRecords **之前**）；values 已常规口径。
- **entry.html**：records 默认过滤常规 + 同款切换；**meta 计数、edited 徽标、日期范围跟随当前视图**（含 hero-overview 分支）。
- **entries.html**：entries_index 已常规口径，不加切换（非常规词条不可搜，属预期；仍可从 hero 页切换查看）。
- 切换用本地 state（项目无 URL 切换先例）。
- 已知 cosmetic：all-modes 视图下非常规-only 词条无数值 chips（values 常规口径）、mixed 词条省略非常规点。

### D4 徽标样式（style.css）

`.badge.mode-*` 各模式配色（社区/愚人节/实验/试玩/PTR/公告）。

## [S3] Out of Scope

- 标题规则之外的人工清单（用户选仅标题规则）。
- entries.html 的非常规词条搜索与切换。
- 非常规模式的数值轨迹（values 仅常规口径）。
- 解析层/hash 变更（无）。

## Tasks

- [x] T1: 特性文档 — acceptance: 本文档含设计与任务（covers: 全部）
- [x] T2: modes.py 标题规则 — acceptance: 各模式命中（含 CN 完全正常）、大小写变体不误伤（covers: D1）
- [x] T3: pairing.py patches_index mode — acceptance: p-2025-04-01-1 判 april_fools（CN 侧兜底）、unpaired 用自身（covers: D2；depends: T2）
- [x] T4: build_hero_files 打标 + values 常规口径 — acceptance: 记录带 mode、CN 愚人节记录判 april_fools、values 无非常规点（covers: D2；depends: T3）
- [x] T5: entries_index 常规口径 — acceptance: 词条仅常规统计、非常规-only 词条消失、总数 956（covers: D2；depends: T4）
- [x] T6: 前端默认过滤+切换+徽标 — acceptance: hero/entry 默认无非常规记录、切换可见（含 hero-overview meta）；index/patch 徽标正确（covers: D3 D4；depends: T5）
- [x] T7: 测试与 smoke 重基线 — acceptance: pytest/smoke 全过（covers: 全部；depends: T6）
- [x] T8: rebuild 重生成 + 独立 review + 规格定稿 — acceptance: review 无 critical、status: delivered（covers: 全部；depends: T7）
