---
feature: contentstack-parse
status: in-progress
updated: 2026-08-23
branch: feat/contentstack-parse
commits: # filled at delivery
---

# CN 2月11日补丁归档：Contentstack 格式解析支持

## Report

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

- [ ] T1: spec 文档 + worktree — acceptance: 本文档含设计与任务；`.worktrees/contentstack-parse` 分支 `feat/contentstack-parse`（covers: 全部）
- [ ] T2: parse.py contentstack 支持 + 正则修正 + 守卫 + 单测 — acceptance: test_parse 新 fixture 用例全绿（covers: D1-D4；depends: T1）
- [ ] T3: 定向归档 2026-02 CN + 验证 — acceptance: cn-2026-02-11-1.json 存在（22 节/47 英雄）、p-2026-02-09-1 配对成立、仅预期数据文件变化（covers: D5；depends: T2）
- [ ] T4: smoke 计数重基线 + 全量验证 — acceptance: pytest/smoke/layout 全绿、rebuild 双跑幂等、真实浏览器 02-11 补丁页可渲染（covers: D5；depends: T3）
- [ ] T5: 独立 review — acceptance: review 无 critical（covers: 全部；depends: T4）
- [ ] T6: 独立 review + 规格定稿 — acceptance: status: delivered、Report 填毕（covers: 全部；depends: T5）
