---
feature: patch-archive
status: delivered
updated: 2026-08-15
branch: feat/patch-archive
commits: 5ab4fc1..b295273
---

# 守望先锋补丁说明监控与留档系统

## Report

**What was built** — 用 GitHub Actions 监控《守望先锋》英文/中文官网补丁说明的完整留档系统。抓取器按月枚举两站全部历史（英文 2016-05 至今 124 个月、中文 2025-02 至今 19 个月），解析器用文本分片技术处理网易站未闭合 HTML 并把 2016 老格式降级为整段原文，产出 395 条补丁的双重存档（可读 Markdown + 结构化 JSON）。系统对每条补丁计算内容哈希，每 6 小时轮询发现新补丁或官方事后修改，自动提交入库、写 changelog、开 GitHub Issue 并发邮件。英雄/技能改动被解析成 53 个英雄的轨迹时间线（中英双语、威能新增/移除/重做状态、数值 before→after），通过 GitHub Pages 静态查询站和 CLI 查询。

**Verification** — `pytest -q`：28 passed（解析/名称映射/diff/流水线/通知）。全量回填：EN 341 + CN 54 补丁、53 英雄轨迹、数据 9.9MB，与页面内嵌 `patchNotesDates` 权威月份列表一致。幂等重扫 143 个月 0 变化（门控正确：无变化不产生 commit/notify）。本地 serve 冒烟：index/heroes_index/hero JSON/hero 页全部 200。monitor 工作流的 Issue 生成命令以显式 UTF-8 验证标题/正文渲染正确。两轮独立审查（5ab4fc1..e99acfd 主审查 + f93f031/b295273 修复复审）通过；P1（邮件失败不应阻断提交）、P2（空 slug 数据污染、GITHUB_TOKEN 不触发 pages 部署）及 P3 均已修复。

**Journey log** —
1. 网易中文站 HTML 存在未闭合 div（深度追踪发现补丁边界处深度 1→4），树形解析不可靠——改用按开标签文本切分后逐片解析，顺带解决了补丁互相嵌套产生的幻影补丁。
2. 中文站"士兵：76"全角冒号、"Solider: 76"官方拼写错误、"McCree"退役名——名称解析需要别名表 + 全角标点归一化 + 音调不敏感匹配，三管齐下。
3. Stadium 模式的面具物品块（"Ramattra Mask"/"“士兵：76”面具"）被当作英雄解析进轨迹，需按名称后缀过滤且保留在归档原文中。
4. 纯中文英雄名 slugify 会返回空串导致时间线条目全部落到 `""` 键下丢失——兜底为确定性 hash slug，并以此发现 names.json 缺 3 个新英雄。
5. 内容哈希在名称富化前计算，names.json 的增补永远不会误报"官方修改"。

## [S1] Problem

《守望先锋》官方补丁说明（英文站 overwatch.blizzard.com / 中文站 ow.blizzard.cn）是网页形态，无法查询英雄/技能的历史改动轨迹；且 Blizzard 偶尔会事后编辑旧补丁内容，普通用户无从感知。需要一个自动化系统：定时抓取两站补丁、格式化归档进 GitHub 仓库、把改动解析成结构化数据以支持"查士兵76子弹伤害历史"这类查询，并在出现新补丁或旧补丁被修改时通知用户。

## [S2] Design

### 数据获取（已实测验证）

- 英文站月份 URL：`https://overwatch.blizzard.com/en-us/news/patch-notes/live/{YYYY}/{MM}/`，2016-05 至今逐月齐全，纯服务端渲染；权威月份列表取自页面内嵌 JS 变量 `patchNotesDates.live`。
- 中文站月份 URL：`https://ow.blizzard.cn/news/patch-notes/live/{YYYY}/{MM}/`，仅 2025-02 至今；必须带尾斜杠；无补丁月份返回 404（作为"无补丁"信号）；月份只能枚举。
- 两站 HTML class 结构一致，解析器共用。补丁标识：EN 锚点 `id="patch-YYYY-MM-DD"`；CN 从标题 `《守望先锋》补丁说明——YYYY年M月D日` 提取日期。
- 抓取策略：requests.Session + 浏览器 UA，1 req/s 限速，失败 3 次指数退避重试（404 直接视为该月无补丁）。

### 数据模型

- patch id：`{site}-{YYYY-MM-DD}-{seq}`（seq 解决同天多补丁）。
- 每个补丁产出双文件：`data/archive/{site}/YYYY/MM/YYYY-MM-DD-seq.md`（人类可读）+ `data/patches/{site}/YYYY-MM-DD-seq.json`（结构化）。
- patch JSON：`{id, site, date, url, title, hash, sections[]}`；section 分 `hero_update`（heroes[]）与 `generic_update`。
- hero_update.heroes[]：`{slug, name_en, name_cn, perks[], abilities[]}`；ability：`{name_en, name_cn, slug, changes[]}`；change：`{text_en, text_cn, before, after, metric}`（before/after/metric 可空，原文必须保留）。
- perk：`{name_en, name_cn, status: added|removed|reworked|moved|changed, lines_en[], lines_cn[]}`。
- 英雄轨迹 `data/heroes/{slug}.json`：`{slug, names{en,cn}, role, timeline:[{patch, date, site, url, patch_title, kind, ...}]}`，每次入库由全部 patches 全量重建；条目按能力/威能/通用分组，数值改动含 before/after。
- 名称映射 `data/names.json`：键=英文原文 → `{cn, slug, role}`；技能名同表。查表支持别名（Solider: 76/McCree）、音调不敏感、CN 全角标点归一化。未命中 → 确定性 slug（纯 CJK 用 hash 兜底，绝不返回空串）+ unknown 告警清单（不失败 CI）。
- 数值提取：EN `(\w[\w ]+?) (increased|reduced|decreased|changed) from (\d+(?:\.\d+)?) to (\d+(?:\.\d+)?)`；CN `([\u4e00-\u9fff]+)从(\d+(?:\.\d+)?)[点秒米度%]?(提高|缩短|降低|减少|增加|扩大|延长)至(\d+(?:\.\d+)?)[点秒米度%]?`。
- 2016 老格式（OW1 时代）解析不到结构时，降级存整段 `raw_text`（已剔除 "Top of post" 等站点 chrome）。

### 变化检测与通知

- 每个 patch 的 `hash` = 规范化 JSON（剥 hash 字段）sha256，**在名称富化前计算**（names.json 增补不误报修改），存 `data/manifest.json`。
- 每次运行：新 id → `new`；hash 变化 → `modified`（官方事后编辑），深度 diff 逐条写入 `data/changelog.jsonl`。
- 两种变化都触发：GitHub Issue（gh 创建，含变化摘要 + 源 URL）+ SMTP 邮件（合并 EN/CN 一封，**best-effort，任何失败只打 WARN 不阻断提交与 Issue**）。
- 无变化 → 零 commit、零通知。monitor 每 6 小时 cron + 可手动 dispatch。

### 查询

- GitHub Pages 静态站 `web/`（纯 HTML + 原生 JS，无构建链）：英雄列表页（按职责分组 + 搜索）+ 英雄详情页（按技能/威能/通用分组的改动时间线，中英双语，数值高亮，每条链接官方原文）。
- CLI `tools/query.py`：`python tools/query.py <slug|中文名|英文名>`，支持 `--site --date` 查单补丁（含同天多补丁）、`--json` 输出原始数据。

### GitHub Actions

- `monitor.yml`：cron 每 6 小时（避开整点）+ dispatch；pip install → pipeline 增量 → 有变化则 commit+push → gh issue → SMTP 邮件（邮件失败不阻断 run）。Secrets：`SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/SMTP_TO`。权限 `contents: write, issues: write`。
- `backfill.yml`：手动 dispatch 全量回填，一次性 commit（数据已在仓库，按年分批仅对首次回填有意义），不通知。
- `pages.yml`：push main + 每日 cron + dispatch → configure-pages → 拷贝 web/ + data/ 到 _site/ → deploy-pages。权限 `pages: write, id-token: write`。说明：monitor 的自动 commit 由 GITHUB_TOKEN 推送，按 GitHub 规则不触发同仓库 `on: push` 工作流，故 pages 用每日 cron 兜底刷新。
- `ci.yml`：push/PR 运行 pytest。

## [S3] Out of Scope

- 不存原始 HTML 快照（changelog 已记录文本 diff）。
- 不做 EN/CN 补丁日期配对或翻译对齐（各站独立归档，查询站按英雄 slug 聚合）。
- 不用 LLM 解析（规则解析 + names.json 足够，CI 零成本、可复现）。

## Tasks

- [x] T1: 抓取模块 `src/ow2_patch/fetch.py`（EN 月份枚举 + 单月抓取，含 2016 样例结构确认） — acceptance: 本地拉下 EN 某月 HTML 入 cache，2016 样例页真实结构已确认 (covers: S2-数据获取)
- [x] T2: 解析模块 `model.py` + `parse.py` — acceptance: `tests/test_parse.py` 全绿，EN/CN/2016 降级/同天多补丁样例全对 (covers: S2-数据模型; depends: T1)
- [x] T3: 名称映射 `data/names.json` 初版（OW2 全部英雄+技能）+ slug 生成 — acceptance: 样例英雄/技能全部命中映射，unknown_name 机制生效 (covers: S2-数据模型; depends: T2)
- [x] T4: 变化检测 `diff.py` + manifest + changelog — acceptance: `tests/test_diff.py` 全绿，人为改动 fixture 判为 modified (covers: S2-变化检测与通知; depends: T2)
- [x] T5: 通知 `notify.py`（Issue 正文 + SMTP 邮件） — acceptance: `--dry-run` 渲染的 Issue/邮件正文正确，SMTP 测试邮件收到 (covers: S2-变化检测与通知; depends: T4)
- [x] T6: 全量回填（EN 2016-05~今 + CN 2025-02~今）+ 英雄轨迹生成 — acceptance: 本地全量落库，patch 数与 patchNotesDates 一致，heroes/*.json 生成 (covers: S2-数据模型, S2-查询; depends: T5)
- [x] T7: 查询站 `web/` — acceptance: 本地 http.server 打开英雄详情正常展示时间线 (covers: S2-查询; depends: T6)
- [x] T8: 三个 workflow yml + 接远程 + secrets + 端到端验证 — acceptance: GitHub dispatch monitor/pages/backfill 全部跑通，Pages 上线，收到真实 Issue + 邮件 (covers: S2-GitHub Actions; depends: T7)
