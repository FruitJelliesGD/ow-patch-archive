---
feature: crossover-category
status: in-progress
updated: 2026-08-23
branch: feat/crossover-category
commits: # filled at delivery
---

# 「联动」徽章：crossover 内容分类

## Report

## [S1] Problem

时间浏览页缺少「联动」徽章——守望先锋与其他品牌（含暴雪自家 IP）的联动补丁（一拳超人/LE SSERAFIM/星际牛仔/保时捷/变形金刚/我的英雄学院/街霸6/心之怪盗团/魔兽/暗黑等 15 个）无任何标识，无法筛选。

## [S2] Design

### D1 categories.py 新增 `crossover` 类别

- `CATEGORY_RULES` 在 `owl` 后追加：`("crossover", r"collab|One[- ]?Punch Man|LE SSERAFIM|Cowboy Bebop|Transformers|Warcraft|My Hero Academia|Phantom Thieves|Street Fighter|Porsche", r"心之怪盗团")`
- `CATEGORY_LABELS` + `"crossover": "联动"`；`CATEGORY_SCOPES` + `"crossover": TITLE_SECTIONS`。
- `CATEGORY_ORDER` 位置：`owl` 之后（末尾内容类别）。
- 短语精简原则：仅保留有命中的短语（全量 399 补丁验证零误判）；CN 联动标题用拉丁品牌名，EN 短语代劳，仅怪盗团需 CN 短语。正文误判（Avatar 头像/合作/One Punch 高光/一拳/A 段皮肤 bug）全部被 TITLE_SECTIONS 排除。

### D2 手动标记（data/manual_categories.json）

- `en-2023-10-10-1`：`["season"]` → `["season", "crossover"]`（Diablo Trials of Sanctuary，正文-only）；
- `en-2019-10-15-1`：新增 `["crossover"]`（BlizzCon 伊利丹/泰兰德，正文-only）。

### D3 前端（web/app.js + style.css）

- `CATEGORY_LABEL`/`CATEGORY_ORDER` mirror + `crossover: "联动"` / `"crossover"`。
- `.badge.mode-crossover { background: rgba(236, 64, 122, 0.18); color: #f06292; }`（粉/品红，唯一未用色相）。

### D4 测试

- `test_categories.py`：`test_category_tables_complete` 14→15；参数化正/负例；`test_crossover_title_sections_scope`。
- `test_pairing.py` real-data 不变量：15 个 id 含 `crossover`；`en-2024-10-28-1`（All Might 皮肤 bug）、`p-2026-02-09-1`（cn-2026-02-11 联动 dev-note）不含；计数 15。

### D5 数据与 smoke

- rebuild：15 个索引条目 +`crossover`（仅 patches_index.json 变化）。
- smoke：chipCount 16→17；其余计数不变。

## [S3] Out of Scope

- 未来新品牌的短语扩展（记录于 D1 精简原则；必要时手动补短语或 manual_categories）。
- 纯中文「联动」标题识别（CN 侧仅心之怪盗团，接受的 minimal-list 取舍）。
- 前端筛选 URL 回写等（既有机制不变）。

## Tasks

- [ ] T1: spec 文档 + worktree — acceptance: 本文档含设计与任务；`.worktrees/crossover-category` 分支 `feat/crossover-category`（covers: 全部）
- [ ] T2: categories.py crossover + 前端 + 测试 — acceptance: test_categories 新旧用例全绿（covers: D1 D3 D4；depends: T1）
- [ ] T3: manual_categories +2 + rebuild — acceptance: 15 条目含 crossover、计数 15、仅 patches_index.json 变化（covers: D2 D5；depends: T2）
- [ ] T4: smoke 重基线（chipCount 17）+ 全量验证 — acceptance: pytest/smoke/layout 全绿、rebuild 双跑幂等、真实浏览器抽查（covers: D5；depends: T3）
- [ ] T5: 独立 review — acceptance: 0 critical（covers: 全部；depends: T4）
- [ ] T6: 独立 review + 规格定稿 — acceptance: status: delivered、Report 填毕（covers: 全部；depends: T5）
