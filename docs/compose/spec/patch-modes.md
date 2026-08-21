---
feature: patch-modes
status: in-progress
updated: 2026-08-22
branch: feat/patch-modes
commits: <base-sha>..<head-sha> # filled at delivery
---

# 常规/非常规模式补丁区分（迭代十一）

## Report

## [S1] Problem

英雄轨迹、词条、数值轨迹混入了非常规模式补丁（社区模式 Quick Play: Hacked、愚人节、6v6 实验、英雄试玩、PTR、公告）的英雄改动数据——实证非常规记录 **635/10,788（5.9%）**（EN 侧 491 + CN 愚人节 144），愚人节补丁一个就改 40+ 英雄。这些临时模式改动与常规天梯平衡无关，混入常规历史产生误导（如某英雄"伤害从 50 降至 45"实际来自愚人节补丁）。目标：区分常规/非常规补丁，非常规数据**不干扰常规历史**——英雄轨迹/词条/数值轨迹默认只显示常规、可切换查看非常规；首页时间浏览与补丁详情页列出全部补丁并带模式徽标。

## [S2] Design

### D1 标题规则（src/ow2_patch/modes.py，仅标题规则）

`patch_mode(title) -> str` 按优先级正则匹配（re.I）：

- `Quick Play:? Hacked` → `quick_play_hacked`（社区模式）
- `Really, Really, Really Balanced|Totally Normal|完全正常` → `april_fools`（**CN 关键词兜底**——cn-2025-04-01-1 标题为「完全正常的"完全正常先锋"补丁说明」）
- `6v6 Experiment` → `experiment_6v6`
- `Hero Trial|英雄试玩` → `hero_trial`
- `\bPTR\b` → `ptr`
- `Unauthorized Peripheral|Welcome to Overwatch` → `announcement`
- 默认 `standard`

`MODE_LABELS`（py）+ 前端 JS 镜像：`{quick_play_hacked: 社区模式, april_fools: 愚人节, experiment_6v6: 实验模式, hero_trial: 英雄试玩, ptr: PTR 测试服, announcement: 公告}`。**已知局限**：未来新模式标题无规则 → 默认 standard 漏判（用户接受仅标题规则）。

### D2 数据层（mode 以 patches_index pair 级为唯一权威）

- **pairing.py → patches_index**：每个条目加 `mode`——pair 取 en/cn **任一侧非 standard**（en 优先）；unpaired 用自身 title 判定；同时提供 **patch_id → mode**（pair 两侧同 mode，供 build_hero_files 反查——CN 愚人节经 pair 兜底判为 april_fools）。
- **build_hero_files**（pipeline.py）：读 patches_index 建 patch_id→mode 映射（缺省 `patch_mode(title)` 兜底）；每条时间线记录加 `"mode"`（**全部记录保留**供前端切换）；**values 只喂常规记录** `build_values([e for e in entries if e.mode == "standard"])`（数值轨迹默认常规）。
- **build_entries_index**（entries.py）：**常规口径**——只统计 `mode == "standard"` 记录（count/edited/first/last_date 基于常规）；非常规-only 词条（实证 24 个：21 ability + 1 weapon mauga::incendiary-chain-gun + 1 hero_attr wrecking-ball::move_speed + 1 perk wuyang::falling-rain）从检索消失（常规口径的预期结果）。
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
- [ ] T8: rebuild 重生成 + 独立 review + 规格定稿 — acceptance: review 无 critical、status: delivered（covers: 全部；depends: T7）
