---
feature: patch-detail-increments
status: delivered
updated: 2026-08-20
branch: feat/patch-detail-increments
commits: c1e5938..6d5fa30
---

# 补丁页增量：内联加粗 + 目录侧边栏 + 旧补丁图标

## Report

**What was built** — 三项补丁页增量：(1) **内联加粗**：解析器 `_inline_raw` 把官方 `<strong>/<b>` 编码为 `**bold**` 标记（嵌套只留外层），web `inlineBold` 在 esc→`<br>` 之后、numberify 之前还原为 `<strong>`；第三次全量 `--force-rewrite` 迁移使 124 个补丁、1351 处加粗进入数据与 Markdown 归档。(2) **目录侧边栏**：渲染时为章节/英雄/卡片赋唯一 id（`sec-`/`hero-`/`blk-` 索引计数），`buildToc` 生成两级粘性目录（`IntersectionObserver` 滚动高亮、空目录隐藏、移动端 900px 断点隐藏），patch 页加宽至 1180px 双栏。(3) **旧补丁图标**：`renderRawText` 在 103 个 OW1 `raw_text` 中按名称匹配注入英雄头像与技能图标（53 英雄 + 5 别名 + 513 技能键，双边界大小写敏感、首处出现、歧义技能按最近英雄消歧、全量 esc 防 XSS，懒加载 heroes_index/ability_map 失败回退纯文本）。顺带修复规划期发现的 smoke 假阳性（`en-2026-08-14-1` 不在索引致断言基于残留 DOM，改用 `p-2026-08-11-1`/`en-2016-07-19-1`）与 initPatch 残留渲染。

**Verification** — `pytest -q` → 151 passed（含 strong 编码边界断言）；`node tools/_smoke_web.js` → ALL WEB ASSERTIONS OK（含 `strong>Choose your path`、TOC 66 条与 `#sec-0`、legacy-icon 与 `ana.png`、legacy TOC hidden）；第三次 force-rewrite → 143 月全抓 0 错误，重扫当月 0 events；rebuild 3 次字节收敛；download_icons → 614 refs / 0 new / 0 缺失，`git diff` 无 icon 字段移除；独立审查两节全过（规格/正确性/一致性），无 critical，6 项非 critical 建议中采纳 2 项（smoke 加粗断言具体化、TOC 空标题跳过）。

**Journey log** — ① `_inline_raw` 只处理子元素的 strong：`_li_text` 逐子调用时 strong 自身作参数不触发分支，需在函数开头补"元素本身是 strong"的包装。② smoke 测试代码位于模板字符串内，正则必须写双反斜杠（`\\/`），单斜杠会被模板转义吃掉导致"Invalid regular expression flags"。③ 加粗断言须匹配实际结构：`**Choose your path through the Battle Pass.**` 的 strong 包裹整句，"Choose your path" 后跟 " through" 而非闭合标签。④ `_text`（get_text 链）与 `_inline_text`（_inline_raw 链）的分工是 `**` 只进富文本的结构性保证。⑤ 迁移必须本机（国内 IP）执行（CN drift 保护），第三次迁移仅 124/397 个补丁变化（其余字节稳定），验证了解析器的确定性。

## [S1] Problem

上一特性交付了补丁页的段落/列表/图标支持，仍有三处差距：

1. **内联加粗丢失**：官方 HTML 的 `<strong>/<b>`（列表前导句如 "**Choose your path**…"、段落小标题如 "**Hitbox Changes**"）被解析器完全剥离，卡片内文字无强调层级。
2. **长补丁无导航**：补丁页单列 960px 布局，无目录/锚点/滚动定位，几十个英雄的大补丁（如 2026-08-11 有 40+ 英雄）难以浏览。
3. **旧补丁无图标**：2016-2020 的 OW1 补丁（103 个 EN legacy raw_text）以纯文本整段显示，无任何图标。

## [S2] Design

### D1 内联加粗保留（R1）

- 解析器 `_inline_raw(el, in_strong=False)`：`<strong>/<b>` 输出 `**` + 递归内容（in_strong=True）+ `**`（嵌套只留外层）；仅影响 `_rich_text` 链（description / block.body / raw_text），`_text` 不动。
- web 新增 `inlineBold(html)`：`**...**` → `<strong>`；`renderRich`/`renderList` 输出顺序：切段 → esc（XSS）→ `\n`→`<br>` → inlineBold → numberify。
- `render.py` 无需改动（`**` 在 Markdown 天然成粗体）。
- 数据变化导致 hash 一次性 churn，由第三次 `--force-rewrite` 迁移收敛。

### D2 目录侧边栏（R2）

- `initPatch` 渲染时为 `section h2` / `hero h3` / 卡片 `.entry` 赋唯一 id（`sec-{i}`、`hero-{s}-{h}`、`blk-{s}-{b}`，索引计数——数据中同 hero / 同 h2 / 同 block 标题单补丁内可重复），同时收集 `tocEntries=[{id,text,level}]`。
- 新增 `buildToc(entries)`：渲染 `<a href="#id">` 两级列表（level>1 加 `.toc-l2`）；空则 `hidden`；`IntersectionObserver` 滚动高亮（无 IO 时降级跳过，兼容 smoke shim）；锚点跳转用原生 `<a href="#id">`。
- `patch.html`：body 加 `class="patch-page"`；`main` 内改 `.patch-layout`（grid 230px + 1fr），`aside#patch-toc` 粘性定位，渲染目标改为 `#patch-article`。
- CSS 全部作用域在 patch 页：`body.patch-page main { max-width: 1180px }`、`.patch-toc` sticky、`scroll-margin-top`、`.legacy-icon`、`@media (max-width:900px)` 隐藏侧栏（全站首个媒体查询）。

### D3 旧补丁图标注入（R3）

- 仅 `patch.raw_text` 存在时懒加载 `data/heroes_index.json` + `data/ability_map.json`（失败回退纯文本）。
- 匹配键：53 英雄 en 名 + 去重音变体（Lúcio/Lucio 双写法）+ 内嵌别名表（McCree→cassidy 等 5 条，来自 names.py HERO_ALIASES）+ ability_map `by_en` 513 键。
- 匹配规则：`(?<![A-Za-z0-9])name(?![A-Za-z0-9])` 双边界、大小写敏感、首处出现注入（Set 去重）。
- 歧义技能（仅 3 个 slug 多英雄，均非 OW1 时代）：全部匹配按位置排序线性组装，记录最近注入的英雄 slug，歧义技能仅当最近英雄 ∈ 其 heroes 才注入。
- 注入文本保留原文匹配片段 `esc(m[0])`（McCree 显示为 McCree）；图标 `iconImg(path, alt, "legacy-icon")`；全量 esc + inlineBold 收尾（XSS 安全）。

### D4 顺带修复（规划期发现的已有缺陷）

- `patches_index` 的 id 为配对后的 `p-*`，`tools/_smoke_web.js` 使用的 `en-2026-08-14-1` 查不到 meta 早退，现代补丁断言基于残留 DOM（假通过）→ smoke 改用有效 id。
- `initPatch` 开头清空目标容器，避免重复渲染残留。

## [S3] Out of Scope

- 旧补丁结构化解析（逐英雄/技能语义）——raw_text 名称匹配先行。
- 其他页面（hero/entry/首页）的目录或图标。
- `<em>/<i>` 等其余内联标签（官方正文容器内不存在）。

## Tasks

- [x] T13: 特性文档 — acceptance: 本文档含设计与任务（covers: 全部）
- [x] T14: 解析器 `_inline_raw` 保留 strong 为 `**` — acceptance: fixture 解析出 `**Hitbox Changes**` 等（covers: D1；depends: T13）
- [x] T15: web `inlineBold` + renderRich/renderList 集成 — acceptance: 页面渲染 `<strong>`（covers: D1；depends: T14）
- [x] T16: 目录侧栏（id 注入 + buildToc + patch.html + CSS）— acceptance: 现代补丁显示两级目录、锚点跳转、滚动高亮、移动端隐藏（covers: D2）
- [x] T17: legacy raw_text 名称匹配注入图标 — acceptance: 旧补丁页显示英雄/技能图标且无 XSS/误配（covers: D3）
- [x] T18: 测试（parse 新增断言 + smoke 修 bug 与新断言）— acceptance: pytest 与 smoke 全过（covers: D1 D4）
- [x] T19: 第三次全量迁移 + rebuild 收敛 + 全量验证 — acceptance: 迁移后重扫零事件、pytest/smoke 全过（covers: D1）
- [x] T20: 独立 review 与规格定稿 — acceptance: review 无 critical，status: delivered（covers: 全部；depends: T19）
