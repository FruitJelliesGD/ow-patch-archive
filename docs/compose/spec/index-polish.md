---
feature: index-polish
status: in-progress
updated: 2026-08-22
branch: feat/index-polish
commits: # filled at delivery
---

# 页尾仓库链接 + 补丁内容字数 + 2026-04-01 愚人节识别

## Report

## [S1] Problem

三个用户可见问题：(1) 页面页尾没有仓库地址，访客无法快速找到源码/数据仓库；(2) 时间浏览列表每条补丁只显示标题与徽章，看不出补丁体量（大版本 vs 热修），无法一眼判断重要性；(3) `en-2026-04-01-1`（逻辑对 `p-2026-04-01-1`，改动 50 英雄）实为愚人节补丁——标题常规（"Overwatch Retail Patch Notes - April 1, 2026"）未命中标题关键词，首节却是官方愚人节梗 **"Underwatch Patch Notes"**（CN 侧 "守望后卫补丁说明"），目前被误判为 `standard`，其 50 英雄改动污染常规英雄轨迹/词条/数值历史。

## [S2] Design

### D1 mode：愚人节 section 信号（src/ow2_patch/modes.py）

`patch_mode_with_sections` 在 community_created section 检查之后追加愚人节 section 信号：新增 `_APRIL_FOOLS_SECTION_RE = re.compile(r"Underwatch|守望后卫", re.I)`，任一 section 标题命中 → `april_fools`。与 `_COMMUNITY_CREATED_SECTION_RE` 同一模式（section 信号优于手工清单的既定哲学）。pair 级 mode 取 en 优先 → `p-2026-04-01-1` 判 april_fools，前端自动显示愚人节徽章（`.badge.mode-april_fools` 已存在）。

### D2 数据层：索引增加字数字段（src/ow2_patch/pairing.py）

`build_patches_index` 每个条目增加 `chars_en` / `chars_cn`（镜像 `title_*`/`first_section_*` 模式，unpaired 只填对应侧）：

- **定义**：该侧补丁 JSON 中 `sections` + `raw_text` 内全部字符串长度之和（含中英双语字段，作为补丁体量的一致度量；无则 `0`）。
- **实现**：文件已读取（`_section_titles` 同一次 read），新增递归 walker（`str`/`dict`/`list`，非字符串忽略），无额外 IO。

### D3 前端：时间列表字数显示（web/app.js + web/style.css）

`initIndex()` 补丁条目在标题之后追加 `<span class="patch-entry-chars">N 字</span>`：按显示站点取 `site === "cn" ? (p.chars_cn ?? p.chars_en) : (p.chars_en ?? p.chars_cn)`，`Number(x).toLocaleString()` 千分位；`chars` 为 0/缺失时不渲染。CSS：`.patch-entry-chars { color: var(--muted); font-size: 12px; white-space: nowrap; }`。

### D4 前端：页尾仓库链接（web/*.html 五页）

- `index.html` / `entries.html` / `entry.html`：既有 footer 追加 ` · 仓库：<a href="https://github.com/FruitJelliesGD/ow-patch-archive">github.com/FruitJelliesGD/ow-patch-archive</a>`；
- `hero.html` / `patch.html`：当前无 footer，新增与上述一致的 `<footer>`。

### D5 测试

- `tests/test_modes.py`：`patch_mode_with_sections` 单测——section "Underwatch Patch Notes" → april_fools；"守望后卫补丁说明" → april_fools；普通 section → standard。
- `tests/test_pairing.py`：
  - 字数单测（tmp_path fixture）：构造已知 sections/raw_text → 断言 `chars_en/cn` 精确值；raw_text-only → 等于 `len(raw_text)`；
  - 真实数据不变量：`by_id["p-2026-04-01-1"]["mode"] == "april_fools"`；每条目含 `chars_en/cn` 两键；大补丁（`p-2026-08-11-1`）`chars_en > 10000`。
- `tools/_smoke_web.js`：`entryCards` / `entryMergedCount` / `heroEntryCards` 更新为重生成后的实际值（实现时读取并核对量级合理性）；新增 `indexHasChars`（`findHtml(patch-list, /字/)`）断言。

### D6 数据级联与迁移

`tools/rebuild.py --data data` 重生成，预期改动：`patches_index.json`（mode + chars 字段）、`heroes/*.json`（记录 mode 标注，50 英雄的愚人节记录不再计入常规视图）、`entries_index.json`（常规口径计数下降）。实现时核对 git diff 范围，其余数据应字节稳定。已核实 pytest 无绝对计数断言会被破坏（真实数据测试均为关系型不变量）；smoke 的 3 处硬编码计数（919/17/18）需更新。

## [S3] Out of Scope

- 字数统计不做语言去重/智能加权（中英双语字段都计入，作为一致体量度量）。
- 愚人节识别仅加 section 信号，不动标题关键词（标题关键词已覆盖 2024/2025）。
- 仓库链接不更换图标/样式，仅文本链接。
- 补丁详情页（patch.html）不显示字数（仅时间列表）。

## Tasks

- [ ] T1: modes.py 愚人节 section 信号 + test_modes 单测 —— acceptance: 单测覆盖 Underwatch/守望后卫 → april_fools（covers: D1, D5）
- [ ] T2: pairing.py `chars_en/cn` + 字数单测 —— acceptance: 单测精确值通过；真实数据不变量（两键 + 大补丁 > 10000）通过（covers: D2, D5）
- [ ] T3: `tools/rebuild.py --data data` 重生成 —— acceptance: git diff 范围 = patches_index/heroes/entries_index 三类；`p-2026-04-01-1` mode == april_fools；不变量测试通过（covers: D1, D2, D6; depends: T1, T2）
- [ ] T4: 前端字数显示 + 五页 footer 仓库链接 —— acceptance: smoke 新增字数断言通过；浏览器抽查条目字数与 footer 链接（covers: D3, D4）
- [ ] T5: smoke 计数更新（919/17/18 → 重生成实际值）—— acceptance: `node tools/_smoke_web.js` 全绿（covers: D6; depends: T3, T4）
- [ ] T6: 全量验证 + 独立审查 —— acceptance: pytest/smoke/layout/rebuild 通过，审查 0 critical（covers: D3, D4, D6）
