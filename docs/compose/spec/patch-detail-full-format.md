---
feature: patch-detail-full-format
status: in-progress
updated: 2026-08-22
branch: feat/patch-detail-full-format
commits: <base-sha>..<head-sha> # filled at delivery
---

# 补丁详情页全面兼容官方显示格式（迭代九）

## Report

## [S1] Problem

`web/patch.html` 补丁详情页经迭代六/七/八已覆盖官方格式的大部分（段落/列表结构、英雄头像+技能图标、内联加粗、两级目录、legacy 旧补丁结构化+图标注入）。对照官方补丁页（EN `overwatch.blizzard.com` / CN `ow.blizzard.cn`）逐项审计后仍有 6 处显示格式差距：

1. **地图更新 before/after 对比图完全缺失**：EN 页 `PatchNotesMapUpdate` + `blz-comparison-slider`（before/after 槽位图），CN 页地图内容在「核心游戏模式更新→地图更新」通用块内（标题序列 + `<p><img>` 成对）。解析器未捕获图片（`_inline_raw` 跳过 img），地图 section 因 parse.py:125-126 兜底把 "Busan - Control / Downtown / Before and After…" 拍平进 description，图片内容整体丢失。
2. **章节级开发者注被丢弃**：`<div class="PatchNotes-dev">` 直接挂在 section 下（如 Hero Updates 章节导语 "Several underutilized perks have been replaced…"），`_parse_section` 未捕获——真实内容丢失。
3. **正文超链接丢失**：官方页 `<a href>`（论坛/了解更多链接）只保留文本，href 被丢弃。
4. **章节描述内大图横幅丢失**：sectionDescription 里的 `<img>`（新英雄公告横幅等）被丢弃。
5. **Stadium 英雄物品拍平**：`<p><strong>名 - Power</strong></p>` / `名——异能`、`名 - 稀有度 类型 Hero Item` / `名——稀有武器英雄物品` 标记块及其统计行流入 `hero.general` 扁平行（EN "X - Power" 行还被 attribution `_PERK_NAME_RE` 误标为 perk），无稀有度/类型结构。
6. **开发者注样式非官方**：dev-note 渲染为普通文本，官方为斜体引述样式。

## [S2] Design

### D1 地图更新（MapUpdate + Section.maps）

- 模型 `MapUpdate{map_name, area, before, after}`（before/after 为图 URL）；`Section.maps: list[MapUpdate]`；`Section.type` 增 `"map_update"`；全部进 `_section_to_dict` 序列化。
- **EN 解析**（`_parse_section`）：section class 含 `PatchNotes-section-map_update` → `type="map_update"`，遍历 `.PatchNotesMapUpdate`：`.PatchNotesMapUpdate-name` 为空时沿用上一个非空 name（fixture 实证 Downtown.02/MEKA Base.02 等空名）；每个 `blz-comparison-slider` 的 `blz-image[slot=before|after]` src → 一对 `MapUpdate(area=name, before, after)`。**关掉 parse.py:125-126 的 description 兜底**（map 类型不触发，避免拍平文本）。
- **CN 解析**（`_parse_section` 扫描 blocks）：标题为 `地图更新`/`Map Updates` 的 GenericBlock 子序列含 `<img>` 对时 → 提取进 `section.maps` 并清空该 block body。提取规则（按文档序遍历子元素）：标题含 `——` → 新 `map_name`；其他非「修改前与修改后」标题 → 新 `area`；`修改前与修改后` 标签 → 缓冲 img 两两配对 flush；`<p><img>` → 入缓冲；EOF flush（缓冲 2 张 = (before, after)）。
- **Hash**：`map_name` + `area` 入袋（改名触发 modified）；`before`/`after` URL 为富化数据不入袋（同 icon 语义）。`deep_diff` 仅跳过 `.maps[<i>].before` / `.maps[<i>].after`（路径含 `.maps[` 且以 `.before`/`.after` 结尾）——地图改名仍可见。
- **下载**：`tools/download_icons.py` 增 kind `"map"` → `web/assets/maps/{patch_id}/{i}-before.png|-after.png`；URL 优先 netease 主机（CN 可访问）否则 contentstack/cloudfront；https + magic bytes 校验 + 幂等增量。
- **Markdown**（render.py）：`## {title}` 后每图输出 `#### {map_name} {area}` + `- 修改前: {url}` + `- 修改后: {url}`。
- **Web**（initPatch）：`section.maps || []` → `.map-update`：名称头 + `.map-compare` 两个 `<figure>`（`修改前`/`修改后` 标签），img `loading="lazy"` + onerror 隐藏。

### D2 章节级开发者注（Section.dev）

- 模型 `Section.dev: str | None`。`_parse_section` 收集 section 直接子级 `.PatchNotes-dev`（首个非空）；legacy `_parse_legacy_chunk` 中 dev 无 hero/block 可挂时落 `sec.dev`（现状 continue 丢弃）。
- Hash 袋（`patch_canonical_texts` 与 `_dict_canonical_texts` 同步补）`section.dev`。
- render.py：description 后 `*开发者注：{dev}*`。
- Web：section 标题后渲染 `.dev-note`（样式见 D6）。

### D3 正文超链接（`[text](url)`）

- `_inline_raw`：`<a href>` 且 href 为 `https?://` → 输出 `[text](url)`（其余保持纯文本）；`_text` 链不动（同 `**` 先例：只进富文本链 description/block body/raw_text）。
- Web 新增 `media()` 单遍合并正则（避免 imgs 先行生成 `<img>` 后被 linkify 污染属性）：
  `/(!\[([^\]]*)\]|\[([^\]]+)\])\s*\(([^)]+)\)/g`——`![alt](url)` → `<img loading="lazy" onerror=隐藏>`；`[text](url)` → `<a target="_blank" rel="noopener">`；url 已 esc 且仅 `https?://` 白名单（其余原样返回）。处理链统一为 `切段 → esc → \n→<br> → inlineBold → media → numberify`，应用于 `renderRich`/`renderList`/`renderRawText`（收敛为一个后处理助手）。
- render.py 无需改（Markdown 原生支持）。

### D4 章节描述内大图（`![alt](src)`）

- `_inline_raw`：`<img src>`（https）→ `![alt](src)`（hero/ability 图标走 `_icon()` 专用捕获，不经 `_rich_text` 链，不受影响）。
- Web：media() 渲染为热链 `<img>`（不本地下载——横幅罕见且为装饰内容，onerror 优雅隐藏；与 icon 本地化策略的差异记录在案）。
- Hash：src 作为 description 文本入袋（官方换图=内容变化；与 maps URL 排除的差异是刻意的）。

### D5 Stadium 物品（StadiumItem + hero.stadium_items）

- 模型 `StadiumItem{name_en, name_cn, rarity, kind(weapon|ability|survival|power), status, lines_en, lines_cn, raw_text}`；`HeroUpdate.stadium_items: list[StadiumItem]`。
- **解析**（`_parse_general_updates`，先于 perk 判定）：
  - EN：`^(.*?)\s*-\s*(?:Power|(?:Common|Rare|Epic|Legendary|Mythic)\s+(?:Weapon|Ability|Survival)\s+Hero\s+Item)\.?(?:\s+(.*))?$`
  - CN：`^(.*?)——(?:异能|(?:普通|稀有|史诗|传说|神话)(?:武器|技能|生存)英雄物品)\.?(?:\s*(.*))?$`
  - 标记行后随 `<ul>` → `lines`；同行内联 body（"Aftershock - Power Increased…"）→ `lines[0]`；`raw_text=[标记行全文]`（保真）；status 由行首词推导（New/Removed./Reworked from/Changed from；CN 新增/移除/重做/更改为，复用 `_perk_status` 逻辑）。
  - 与 perk 正则无冲突（perk 用 `Minor|Major Perk` / `主要|次级威能`，已实证）；attribution/normalize 不改（迁移后 general 不再含这些行）。
- **Hash**：`raw_text + lines_en + lines_cn` 全入袋（items 不经 attribution 搬运，fresh/stored 天然一致；与 perk「只取 raw_text」的差异因无搬运而安全）。
- **时间线**：`build_hero_files` 增 items 循环 → 以 `kind:"general"` 入时间线（保持现状——今日这些行就是 general 时间线条目，d-va.json 实证）；不分类 dimension（"25 Health." 等不再标 hero_attr，可接受）。
- **词条检索**：items 不入 entries_index（延续「general 不纳入」策略）；此前被误标为 perk 的 Stadium 异能条目将离开索引 → smoke 计数断言重基线。
- **Markdown**：`- 物品 **{name}**（{rarity} {kind}）—— {status}` + `  - ` 缩进行。
- **Web**（heroBlock）：`hero.stadium_items || []` → `.entry.stadium-item`：名称 + 稀有度徽标 + 状态 + `.change-list` 行。

### D6 开发者注官方样式（纯 CSS）

`.dev-note`：斜体 + 左侧竖线/浅色底（官方引述样式），作用于 hero dev_note、block.dev、新增 section.dev；另补 `.map-update/.map-compare/.stadium-item/.item-badge`、内容区 `a` 链接样式。

### D7 迁移

- 本机（国内 IP）`python tools/run.py --data data --force-rewrite`（143 月全量重扫，CN drift 保护复用；不写 changelog）→ `tools/rebuild.py` ×3 字节收敛 → `tools/download_icons.py`（补地图图）。
- Hash schema 保持 3（新增字段为袋扩充，一次性 churn 由 force-rewrite 收敛，同迭代六/七先例）。

## [S3] Out of Scope

- 地图 before/after 交互滑块（用户已选**并排双图**）。
- 描述横幅本地下载（热链 + onerror 兜底）。
- Stadium 物品入词条检索 / hero/entry 页面展示结构调整。
- 官方页面像素级视觉还原（仅内容格式兼容 + dev-note 斜体样式）。

## Tasks

- [x] T31: 特性文档 — acceptance: 本文档含设计与任务（covers: 全部）
- [x] T32: model.py 新字段与序列化 — acceptance: JSON 含 `maps[].{map_name,area,before,after}`、`section.dev`、`stadium_items[]`（covers: D1 D2 D5）
- [x] T33: parse.py 地图解析（EN section + CN 块提取 + 描述兜底关闸）— acceptance: en/cn fixture 解析出 MapUpdate 含正确 name 沿用/区域分组与 URL 对（covers: D1；depends: T32）
- [x] T34: parse.py 章节级 dev（含 legacy 兜底）— acceptance: Hero Updates 章节 dev 落 Section.dev（covers: D2；depends: T32）
- [x] T35: parse.py `_inline_raw` 输出 `[text](url)`/`![alt](src)` — acceptance: 富文本链含链接/图片编码，`_text` 链不含（covers: D3 D4）
- [x] T36: parse.py Stadium 物品解析 — acceptance: EN "Rare Weapon Hero Item"/"Power"、CN "异能/英雄物品" 标记+ul 结构化，status 正确（covers: D5；depends: T32）
- [x] T37: diff.py hash 袋与 deep_diff — acceptance: `test_fresh_reparse_after_migration_is_unchanged` 过；maps 改名触发 modified、URL 变化不触发（covers: D1 D2 D5）
- [x] T38: render.py 地图/dev/物品 Markdown — acceptance: 归档 md 含 `#### 地图`、`*开发者注*`、`- 物品 **名**`（covers: D1 D2 D5）
- [x] T39: pipeline.py 时间线 items → general — acceptance: heroes/*.json 含物品行且字节收敛（covers: D5）
- [x] T40: download_icons.py map kind — acceptance: 地图图下载幂等、netease 优先、magic bytes 校验（covers: D1）
- [x] T41: web app.js 渲染（media/section maps/dev/stadium_items/守卫）— acceptance: smoke 断言 maps-compare/stadium-item/link/section-dev 全过（covers: D1-D5；depends: T33 T35 T36）
- [x] T42: web style.css — acceptance: dev-note 斜体、地图并排、物品徽标、链接样式（covers: D6；depends: T41）
- [x] T43: 测试更新（parse/diff/pipeline/download/smoke/layout + 计数重基线）— acceptance: pytest 与 smoke/layout 全过（covers: 全部）
- [x] T44: 全量迁移与验证 — acceptance: 本机（CN IP）force-rewrite 143 月 0 错误、rebuild ×3 字节收敛、重扫当月 0 events、download_icons 补图、serve 预览正确（covers: D7；depends: T43）
- [ ] T45: 独立 review 与规格定稿 — acceptance: review 无 critical、status: delivered（covers: 全部；depends: T44）
