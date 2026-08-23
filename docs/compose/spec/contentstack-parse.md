---
feature: contentstack-parse
status: delivered
updated: 2026-08-23
branch: feat/contentstack-parse
commits: cfdc061..5778d6c
---

# CN 2月11日补丁归档：Contentstack 格式解析支持

## Report

**What was built** — `parse.py` 新增 **Contentstack 格式解析支持**：官网 CN 页面把 2026-02-11 补丁（第1赛季：黑爪之治发布）渲染为无 `PatchNotes-patch/section` 包装类的扁平 `<div contentstack-unique-entry-key=...>` 序列（294 键、15 种键路径、22 节、47 英雄块），原包装类切分解析器将其整体丢弃。新解析器在文本切分后按 `title` 键分组提取（支持同页多块），字段映射到 Patch/Section/GenericBlock/HeroUpdate（`change_description` 复用 `_parse_general_updates`，与正常 CN 解析形状一致；`metadata.*` 十六进制 GUID 跳过）。**归档完成**：`cn-2026-02-11-1.json`（22 节、35 个具名英雄 47 块、279 条时间线记录）+ Markdown 归档，并通过标题日期（02-10 vs 02-11 差 1 天）自动配对 `p-2026-02-09-1`（此前 `en-2026-02-09-1` 无 CN 配对）。

- **效果**：补丁页中英双语渲染（22 节、47 英雄块、89 目录项）；英雄时间线/词条检索获得 CN 侧记录（前端配对合并）；entries_index 905→904（配对合并净 -1）；`_CN_PERK_RE` 容忍 `（5v5）/（6v6）` 后缀、英雄名剥 `（全新）/（重做）` 标记、`_parse_section` 防 contentstack 吞并守卫。
- **review**：general-6 全部验收标准 MET、0 critical；2 项 P2 数据质量缺陷全部修复——(1) EN 侧 `_EN_PERK_RE` 不认 `(6v6)` 后缀导致 "Protective Barrier – Major Perk (6v6)" 落入 general、EN/CN 威能数量错位 → ability_map 把奥丽莎 "充能标枪" 误配为 "防护屏障"（修 EN 正则后 EN 2 威能 vs CN 2 威能正确配对）；(2) `_status_from_lines` 不剥全角 `。` 导致 20 个 CN 移除威能状态误判 `changed`（`rstrip(".。")`）。另清理了 EN 重解析产生的假官方编辑记录（解析器迁移非官网改动，从 changelog 移除）。

**Verification** — `pytest -q` → 260 passed（256 基线 +4：contentstack 合成/真实 section9/整月页回归 + EN (6v6) 威能；含移除威能 `。` 回归）；`node tools/_smoke_web.js` → ALL WEB ASSERTIONS OK（entryCards 904 重基线，其余计数不变，官方编辑徽章保持为空）；`python tools/rebuild.py --data data` 双跑字节幂等；`npx --yes -p playwright node tools/_layout_check.js` → 12/12；真实浏览器：`patch.html?id=p-2026-02-09-1` CN/EN 双语渲染（22 节、47 英雄块、89 目录、2 语言按钮）、d-va 时间线含 5 条 cn-2026-02-11-1 记录、EN+CN 合并行正常；数据核对：`charged-javelin.name_cn=充能标枪`、`protective-barrier.name_cn=防护屏障`、CN 移除威能 20 条 status=removed、official_edits 空。

**Journey log** — ① 内容哈希只覆盖原文文本（`patch_canonical_texts`），**派生字段（含 perk status）不参与哈希**——解析器修复若只改派生字段，pipeline 永不重写已归档文件，需 `force_rewrite` 迁移（EN 修复改了文本包正常触发，CN 状态修复走了 force_rewrite）。② 解析器迁移用普通 pipeline 会写 changelog "modified" → 被当作**官方事后编辑**（站点徽章+通知），迁移必须 force_rewrite 或事后清理 changelog（本特性已清理）。③ 审计的"标题限定可全杀"类论断必须数据复核：EN `(6v6)` 威能后缀与 CN `（6v6）` 全半角差异导致 EN/CN 威能数量错位 → 位置 zip 误配能力名，正则修复需双向核对。④ EN 日期无标题回退（`_patch_date` 仅 CN 有标题正则），EN fixture 必须带 `.anchor[id^='patch-']`。⑤ contentstack 页英雄块不产生 abilities（`<p>+<ul>` → general/perks/stadium_items），与正常 CN 解析及 EN 02-09 形状对齐——合并/词条口径一致。

## [S1] Problem

官网 https://ow.blizzard.cn/news/patch-notes/live/2026/02/ 中，2026-02-11 补丁（《守望先锋》补丁说明——2026年2月11日，第1赛季：黑爪之治发布）以 **Contentstack 原始格式**内嵌：扁平 `<div contentstack-field-context=... contentstack-unique-entry-key=...>` 序列（294 键、15 种键路径、22 节、47 英雄），**没有** `PatchNotes-patch`/`PatchNotes-section` 包装类。`parse.py` 按这些包装类文本切分（`_PATCH_SPLIT_RE`/`_SECTION_SPLIT_RE`），无包装的 contentstack 块整块被丢弃 → 该补丁从未归档（`data/patches/cn/` 缺 2026-02-11），`en-2026-02-09-1`（第1赛季发布，标题日期 02-10）一直无 CN 配对。

## [S2] Design

### D1 parse.py 集成（src/ow2_patch/parse.py）

`parse_patch_notes`（L68-82）文本切分循环后追加：

```python
if "contentstack-unique-entry-key" in html:
    patches.extend(_parse_contentstack_patches(html, site, url))
```

- 新 `_parse_contentstack_patches(html, site, url) -> list[Patch]`：soup `find_all("div", attrs={"contentstack-unique-entry-key": True})`（文档序），**`title` 键开新组**（同页多块支持）；组 → `_parse_contentstack_patch(divs, site, url)`。
- 日期复用 `_CN_TITLE_DATE_RE`（L42）取 title div 的 `_text`（contentstack 无 `.anchor[id^='patch-']`）→ `2026-02-11`。
- 合并列表进入现有 seq/id 分配（L77-81）→ `cn-2026-02-11-1`（同日唯一，seq 1）。
- 不干扰正常补丁：检测基于 `contentstack-unique-entry-key` 属性（非 class 令牌），与 `PatchNotes-*` 选择器不相交；同页双格式（本月）下 3 个正常补丁解析零变化。

### D2 字段→模型映射

| 键路径 | 目标 |
|---|---|
| `title` | Patch.title；日期 _CN_TITLE_DATE_RE |
| `sections[N].generic_update\|hero_update.title` | Section.title；role=ROLE_MAP |
| `…description`（markdown） | Section.description = `_rich_text(div)` |
| `…dev_comment` | Section.dev = `_text(div)` |
| `…updates[M].update.title/description/dev_comment` | GenericBlock.title/body/dev |
| `…heroes[K].hero.hero_name` | HeroUpdate.name_cn（剥 `（全新）/（重做）` 后缀） |
| `…hero.change_description` | **复用 `_parse_general_updates(cd_div, site)`** → general/perks/stadium_items（与正常 CN 解析形状一致；不产生 abilities） |
| `…hero.dev_comment` | HeroUpdate.dev_note = `_text` |
| `…hero.metadata.asset_guid/icon_guid` | 跳过（十六进制 GUID；前端用本地图标资源） |

### D3 正则修正 + 守卫

- `_CN_PERK_RE`（L41）容忍 `（5v5）/（6v6）` 后缀：`^(.*?)——(主要|次级)威能(?:（5v5）|（6v6）)?\s*$`（"防护屏障——主要威能（6v6）" 不落入 general；正常 CN 页无此后缀，无回归）。
- 英雄名后缀剥离 `^(.*?)(?:（全新）|（重做）)\s*$`（斩仇/艾什）。
- `_parse_section`（L137-138）soup 创建后 decompose `[contentstack-unique-entry-key]`（防文本切分末块把 contentstack 内容吞进空末节 description，防御性）。

### D4 测试（tests/test_parse.py + tests/fixtures/）

1. `cn_contentstack_synthetic.html`：合成最小块（title + generic 节带 updates + hero_update 节 2 英雄含 `——次级威能`/`——主要威能（6v6）`/普通 `<p>+<ul>`/dev_comment/`斩仇（全新）`/`——异能`）→ 断言 id/节数/perks/（6v6）剥离/general/stadium_items/dev_note/block 映射。
2. `cn_contentstack_section9.html`：真实内容（title + section9 重装 d-va+mauga）→ D.Va general 4 行、毛加 动力弹带 perk、role。
3. `cn_2026_02.html`：真实整月页（截到 PatchNotes-body）→ 4 补丁 `[cn-2026-02-25-1, 19, 14, 11]`、02-11 22 节（9/10/11 role 9/14/8 英雄）、无泄漏。

### D5 归档流程

`run.py --months N` 从"今天"回推（环境≈2026-08-23），无法到达 2026-02 → 定向调用：

```bash
python -c "from ow2_patch.pipeline import run_pipeline; import pathlib; run_pipeline(pathlib.Path('data'), months=[('cn',2026,2)])"
```

→ 写 `data/patches/cn/2026-02-11-1.json` + `data/archive/cn/2026/02/2026-02-11-1.md` + changelog.jsonl + manifest + regenerate_all（配对/patches_index/ability_map/heroes/entries）。

数据影响：patches_index 343 条不变（en-2026-02-09-1 standalone → p-2026-02-09-1 pair，标题日期差 1 天配对成立）；heroes/*.json +47 英雄 CN 记录（与 EN 同改动，前端配对合并）；entries_index +条目 → smoke 硬编码计数重基线。

## [S3] Out of Scope

- EN 侧任何改动（en-2026-02-09-1 已正常归档）。
- contentstack 页的图像资源（icon_guid 为十六进制 GUID，无法映射 CDN URL；前端用本地图标资源）。
- 其他格式异常页面的通用兜底（仅本格式）。

## Tasks

- [x] T1: spec 文档 + worktree — acceptance: 本文档含设计与任务；`.worktrees/contentstack-parse` 分支 `feat/contentstack-parse`（covers: 全部）
- [x] T2: parse.py contentstack 支持 + 正则修正 + 守卫 + 单测 — acceptance: test_parse 新 fixture 用例全绿（covers: D1-D4；depends: T1）
- [x] T3: 定向归档 2026-02 CN + 验证 — acceptance: cn-2026-02-11-1.json 存在（22 节/47 英雄）、p-2026-02-09-1 配对成立、仅预期数据文件变化（covers: D5；depends: T2）
- [x] T4: smoke 计数重基线 + 全量验证 — acceptance: pytest/smoke/layout 全绿、rebuild 双跑幂等、真实浏览器 02-11 补丁页可渲染（covers: D5；depends: T3）
- [x] T5: 独立 review — acceptance: review 无 critical（covers: 全部；depends: T4）
- [x] T6: 独立 review + 规格定稿 — acceptance: status: delivered、Report 填毕（covers: 全部；depends: T5）
