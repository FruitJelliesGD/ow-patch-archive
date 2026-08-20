---
feature: patch-detail-format
status: delivered
updated: 2026-08-20
branch: feat/patch-detail-format
commits: 00e9973..0606ba1
---

# 补丁详情页显示格式与图标

## Report

**What was built** — 补丁详情页（`web/patch.html`）按官方格式显示补丁内容：解析器新增 `_rich_text` 保留段落/列表/换行结构（`<p>`→段落、`<li>`→`- ` 前缀行、嵌套列表 2 空格缩进、`<br>`→换行），应用于通用卡片 `block.body`、`section.description` 与 OW1 旧补丁 `raw_text`；解析器同时捕获官方英雄头像/技能图标 URL（EN cloudfront / CN netease）存入 `HeroUpdate.icon`/`AbilityUpdate.icon`。新增 `tools/download_icons.py` 把图标按 slug 打包进 `web/assets/icons/`（技能按 `{hero}/{ability}` 隔离，规避跨英雄 slug 碰撞），页面渲染头像、图标、项目符号列表、缩进与 pre-wrap 旧补丁文本，全部经 `esc`/textContent 转义防 XSS。新增 `--force-rewrite` 迁移路径（绕过变更检测、不写 changelog），本机全量重抓两站 143 个月份完成一次性格式迁移（397 个补丁 JSON + Markdown 归档 + 620 个图标）；`monitor`/`monitor-fast`/`backfill` 工作流新增图标下载步骤，新英雄/技能自动补图标。

**Verification** — 命令与结果：`pytest -q` → 149 passed（含新增 parse/diff/pipeline/run/download_icons 断言）；`node tools/_smoke_web.js` → ALL WEB ASSERTIONS OK（含 hero-avatar/change-list/ability-icon/raw-text）；本地静态服务 → patch.html/heroes/d-mon.png/abilities/d-mon/surging-strike.png 均 200；`python tools/run.py --data data --force-rewrite` → 143 月全部抓取、0 错误，重扫当月 → 0 events（迁移后监控稳定）；`python tools/download_icons.py` → 620 图标、二次运行 0 new（幂等）；`python tools/rebuild.py` 双跑收敛（第 3/4 次字节一致）。独立审查两轮：首轮发现 1 个 P1（内联片段空格丢失致 legacy 样板清洗失效），修复后复审 0 critical；342/342 存储 hash 与 manifest 一致、4210 图标引用零缺失。已知修复：test_pairing CN 计数 54→55、smoke indexPatches 341→342（数据增长导致的过期断言，非特性引入）。

**Journey log** — ① worktree 中 pytest 默认解析到主仓库的 editable 安装（旧代码），必须在同一命令内设置 `PYTHONPATH=<worktree>/src`，否则 13 项假失败。② 能力 slug 跨英雄碰撞真实存在（quick-melee→4 英雄），图标持久化键必须 hero 作用域。③ `clean_legacy_text` 的样板正则用字面单空格：`raw_text` 带换行后必须先折叠空白再清洗，且解析器拼接内联节点不得丢失片段间空格（`<a>Bug Report </a>forum.`→"Bug Report forum."），否则样板短语无法匹配、旧补丁 hash 嵌入 chrome。④ 迁移必须本机（国内 IP）执行——GitHub runner 抓 CN 站得到英文变体页会被 drift 保护跳过，CN 数据不会重生成。⑤ `regenerate_all` 的 dict 原地改写天然保留新增字段；rebuild 前两次运行会因能力图谱学习收敛，需跑 3 次确认字节稳定。

## [S1] Problem

`web/patch.html` 补丁详情页的显示格式与官方补丁说明差距大：

1. **无换行**：解析器（`parse.py`）把官方 HTML 的段落/列表全部拍平成单空格字符串，数据 JSON 中没有任何换行。通用卡片（Bug Fixes / General Updates / Competitive Play 等）的 `block.body` 是多段落连成的一段文字。
2. **无缩进**：英雄改动行、技能变更行渲染为无项目符号、无缩进、无间距的平铺文本，层级感缺失。
3. **无图标**：官方页面的英雄头像、技能图标 `<img>` 被解析器完全丢弃，页面无任何图标。
4. **旧补丁空白**：2016-2020 的 OW1 降级补丁数据存为 `raw_text`，详情页完全不渲染（空白）。

## [S2] Design

### D1 解析器：保留段落/列表结构

新增 `_rich_text(el)`：按块级子元素序列化保留结构——`<p>` → 文本行 + 空行、`<br>` → `\n`、`<li>` → `- ` 前缀行（嵌套列表缩进 2 空格 `  - `）、`<h*>` → 文本行。应用于：

- legacy 降级 `raw_text`（原来 `get_text(" ")` 单空格连接 → 换行连接）
- `section.description` 与 section 兜底文本
- `GenericBlock.body`

英雄名/技能名/dev_note/general/perk/change 行保持现有逐条结构不变。`- ` 前缀使归档 Markdown（`render.py` 原样写出 body）渲染成真列表。

### D2 图标捕获与存储

- `HeroUpdate.icon` / `AbilityUpdate.icon` 字段：解析器捕获官方 `<img class="PatchNotesHeroUpdate-icon">` / `<img class="PatchNotesAbilityUpdate-icon">` 的绝对 URL（EN: cloudfront.net，CN: netease.com）。
- icon 是富化数据：**不进内容哈希 bag**（与 slug/数值一致），不触发官方编辑检测。
- `deep_diff` 跳过 `icon` 键，避免 changelog/通知噪音。

### D3 图标本地打包（新增 tools/download_icons.py）

- 扫全部补丁 JSON 的 icon URL，按键去重：英雄 `{slug}`、技能 `{hero_slug}/{ability_slug}`（**技能 slug 跨英雄碰撞已证实**：quick-melee→4 英雄等，必须 hero 作用域）。
- URL 选择：优先 netease（cn，国内可访问）否则 cloudfront（en），同站取最新日期（确定性排序）。
- 落盘 `web/assets/icons/heroes/{slug}.png`、`web/assets/icons/abilities/{hero_slug}/{ability_slug}.png`；已存在跳过（幂等增量）；校验图片 magic bytes；https 白名单；`--dry-run`、`--marker`（新增时写 marker 文件）；网络失败仅 WARN 不退出非零（不阻断监控 commit）。

### D4 内容哈希与变更检测

- `clean_legacy_text` 先 `re.sub(r"\s+", " ")` 折叠空白再清洗样板文本——现有样板正则使用字面单空格，`raw_text` 带 `\n` 后必须先折叠否则净化失效（持续误报）。旧数据输出字节不变，无需 bump hash schema。
- 其余哈希逻辑不变。

### D5 force-rewrite 迁移路径

`run_pipeline` 增加 `force_rewrite` 参数 + `tools/run.py --force-rewrite`：

- 绕过 `detect_changes`，逐条 enrich → 重写全部 patch JSON + Markdown → 更新 manifest hash；**不写 changelog、不做 deep_diff**。
- 复用 CN variant drift 跳过保护。
- 末尾照走 `save_manifest` + `regenerate_all`。
- 迁移必须**本机（国内 IP）执行**：GitHub runner（美国 IP）抓 CN 站得到英文变体页会被 drift 保护跳过，CN 数据不会重生成。

### D6 web 渲染

- 新增 `renderRich(el, text)`：按空行分段落 → `<p>`；`- ` 连续行 → `<ul><li>`；`  - ` → 嵌套 ul；段内 `\n` → `<br>`；全部 `esc()` 转义（防 XSS）。
- 新增 `iconImg(path, alt, cls)`：本地相对路径 + `loading="lazy"` + `onerror` 隐藏兜底。
- `initPatch`：description / block.body 改 `renderRich`；新增 `patch.raw_text` 分支渲染 `<div class="raw-text">`（textContent + pre-wrap）。
- `heroBlock`：英雄标题前插头像；general / perk 行 / 技能变更行改 `<ul class="change-list"><li>` + `numberify(esc())`（与 hero/entry 页 numberify 约定对齐）；技能标题前插技能图标。
- CSS：`.hero-avatar` / `.ability-icon` 尺寸圆角、`.text p/ul/li` 间距、`.change-list` 缩进项目符号、`.raw-text` pre-wrap。

### D7 监控工作流自动补图标

`monitor` / `monitor-fast` / `backfill` 在 pipeline 步骤后运行 `download_icons.py`，有新图标时随数据一起提交（新英雄/技能未来自动补充）。

## [S3] Out of Scope

- 地图 before/after 对比图（`PatchNotesMapUpdate` 未结构化解析，保持现状）。
- hero.html / entry.html / 首页的图标（仅补丁详情页）。
- OW1 旧补丁无图标（官方旧页无图标结构）。

## Tasks

- [x] T1: 特性文档 — acceptance: 本文档含设计与任务（covers: 全部）
- [x] T2: 解析器 `_rich_text` 结构保留 + 图标捕获 — acceptance: fixture 解析出含 `\n`/`- ` 的 body/description/raw_text 与 hero/ability icon URL（covers: D1 D2；depends: T1）
- [x] T3: model.py icon 字段与序列化 — acceptance: JSON 含 `"icon"` 字段（covers: D2；depends: T2）
- [x] T4: diff.py icon 键跳过 + clean_legacy_text 先折叠空白 — acceptance: deep_diff 不含 icon 键；带 `\n` 的 raw_text chrome 清洗等价（covers: D2 D4；depends: T2）
- [x] T5: tools/download_icons.py — acceptance: 按 hero/ability 键去重下载、幂等、magic bytes 校验、marker 输出（covers: D3）
- [x] T6: force-rewrite 路径 — acceptance: `--force-rewrite` 全量重写且不写 changelog（covers: D5）
- [x] T7: web 渲染 — acceptance: 详情页显示段落/列表/缩进/图标/raw_text（covers: D6；depends: T3）
- [x] T8: 工作流加图标步骤 — acceptance: 三个工作流含 download_icons 步骤与提交条件（covers: D7）
- [x] T9: 测试更新与新增 — acceptance: 新增断言全部通过（covers: D1 D2 D4 D5）
- [x] T10: 数据迁移与验证 — acceptance: 全量重抓后本机 `python tools/serve.py` 预览格式正确、pytest 通过、次日监控零事件（covers: D5 D6）
- [x] T11: 独立 review 与规格定稿 — acceptance: review 无 critical 发现，规格 status: delivered（covers: 全部；depends: T10）
