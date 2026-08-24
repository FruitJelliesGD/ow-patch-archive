---
feature: hybrid-cn-empty-parse
status: in-progress
updated: 2026-08-24
branch: feat/cn-hybrid-parse
commits: # filled at delivery
---

# 混合格式 CN 补丁解析 + 空内容防护

## Report

## [S1] Problem

CN 官网（ow.blizzard.cn）在 2025/07 月份页把 2025-07-25 补丁渲染为**混合结构**：
一个 Contentstack 标题 div（`contentstack-unique-entry-key="title"`）紧跟着一个
**没有 `.PatchNotes-patchTitle`** 的经典 `<div class="PatchNotes-patch">` 内容块。
这导致（issue #7，commit aced000d）：

- 包装类解析路径（`_PATCH_SPLIT_RE` + `_parse_patch_chunk`）把标题 div 留在首块
  （无 `PatchNotes-patch` 类 → 丢弃），而内容块内只有 `h4.PatchNotes-sectionTitle`
  没有 h1/h2/h3/`.patchTitle` → 返回 None，**内容被静默丢弃**（parse.py:193,196-199）；
- Contentstack 路径（`_parse_contentstack_patches`）只把标题 div 分组 →
  `_parse_contentstack_patch` 发出**仅有 title/date、`sections=[]` 且无 raw_text** 的
  空 Patch（parse.py:117-179），违反 parse.py:8-9 的"内容永不丢失"原则；
- 流水线对空内容补丁无任何防护：`run_pipeline` 照常写 328B 空桩 JSON + 156B
  头-only Markdown、记 manifest 哈希、配对 `p-2025-07-24-1`、更新索引
  （`first_section_cn:""`、`chars_cn:0`），workflow 提交并发 issue，全程绿色；
- 下游症状：详情页渲染空内容（"web页内容为空"）；预览页标题因 app.js:309-311
  `first_section_cn || first_section_en || longTitle` 落到 EN 首节
  "Hotfix Balance Update"（"标题未更新为中文"）。

## [S2] Design

**D1 解析器：合并混合结构（parse.py）**
- `parse_patch_notes`：当某块含 `PatchNotes-patch` 但无标题（`_parse_patch_chunk`
  返回 None 且块含该 class）时，不再丢弃 —— 若已存在一个 sections 为空的
  Contentstack 补丁（标题/日期已由标题 div 确定），把该块的 sections 解析结果
  附加到该补丁（标题、日期、url 沿用）。
- `_parse_contentstack_patch`：组内有 title+date 但解析不出任何 section 时，
  降级为 raw_text（组内 divs 的 `_rich_text`），保证内容不丢；与 wrapper 路径
  (parse.py:216-219) 的降级行为一致。
- 不引入重复：无标题块目前从不产出补丁，附加是纯增量；seq 分配逻辑（parse.py:93-97）不变。

**D2 流水线：空内容新补丁 WARN（不失败）（pipeline.py / run.py / notify.py）**
- `RunResult` 新增 `parse_warnings: list[str]`；`run_pipeline` 对 **kind==new** 且
  `not patch.sections and not patch.raw_text` 的补丁打印 `WARN` 并记录。
- 仍照常 `_write_patch`（写空桩）+ manifest 哈希，保持哈希稳定：下次扫描解析结果
  不变 → 无事件 → 无重复告警；官方页面后续补上内容时哈希变化 → modified 事件
  自动补全归档。
- `tools/run.py emit()` 打印 `result.parse_warnings`。
- `notify.py _render_new`：空内容补丁在 Issue 正文追加
  `> ⚠️ 解析内容为空，需人工检查` 提示行。
- 运行保持成功（用户决策：仅 WARN，不失败，不触发告警 Issue）。

**D3 前端：预览页标题同语言优先回退（web/app.js:309-311）**
- CN 视角：`first_section_cn || title_cn || first_section_en || title_en`；
- EN 视角：`first_section_en || title_en || first_section_cn || title_cn`。
- 效果：CN 首节缺失时显示中文长标题而非英文首节；补录后自然显示中文首节。

**D4 前端：详情页内容缺失兜底（web/app.js:1052）**
- `fetchJSON(file)` 包 try/catch，失败时渲染"该补丁内容暂缺（未归档或解析失败）"
  而非空白页/未处理 reject。

**D5 补录恢复**
- 修复合入 main 并 push 后，monitor 全量扫描重跑：现网页面已有完整内容 →
  cn-2025-07-25-1 产生 modified 事件 → 全量 JSON/MD 写入 + changelog + 重新配对/索引
  → commit → pages 自动重建部署 → 预览页中文标题 + 详情页有内容；issue #7 关闭。
- 存量测试同步：`test_pairing.py` 真实数据配对断言 56 → 57（stub 提交新增
  `p-2025-07-24-1` 配对所致，为 PRE-EXISTING 基线漂移）。

## [S3] Out of Scope

- EN 站点结构变更 / EN 解析器改造。
- 空内容补丁改为"运行失败 + 告警 Issue"（用户已决策：仅 WARN）。
- 清除 stub 提交产生的 changelog 条目（保留为 modified 历史）。
- issue #7 自动关闭（交付后人工确认关闭）。

## Tasks

- [ ] T1: 解析器合并混合结构 + Contentstack raw_text 降级（覆盖: D1）
      — acceptance: 现网 2025/07 页解析出 cn-2025-07-25-1 完整 sections（首节
      "平衡性在线修正更新"）；新 fixture 单测通过。
- [ ] T2: 空内容 WARN（pipeline/run/notify + 测试）（覆盖: D2）
      — acceptance: 新补丁 sections 为空且无 raw_text 时打印 WARN、Issue 正文含
      提示行、运行仍成功；pytest 覆盖通过。
- [ ] T3: 前端标题同语言回退 + initPatch 兜底（覆盖: D3、D4）
      — acceptance: CN 视角条目缺失 CN 首节时显示中文长标题；patch JSON 缺失时
      页面显示"内容暂缺"而非空白。
- [ ] T4: 存量测试同步（配对计数 56→57）（覆盖: D5）
      — acceptance: `pytest -q` 全绿（除记录为 PRE-EXISTING 的基线项）。
- [ ] T5: 补录恢复（覆盖: D5）
      — acceptance: 合入 main 并触发 monitor 全量扫描后，线上索引
      `p-2025-07-24-1` 的 `first_section_cn`/`chars_cn` 非空，详情页有内容，
      预览页中文标题；issue #7 关闭。
