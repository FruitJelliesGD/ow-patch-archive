---
feature: patch-archive
status: in-progress
updated: 2026-08-15
branch: feat/patch-archive
---

# 守望先锋补丁说明监控与留档系统

## Report

（交付时填写）

## [S1] Problem

《守望先锋》官方补丁说明（英文站 overwatch.blizzard.com / 中文站 ow.blizzard.cn）是网页形态，无法查询英雄/技能的历史改动轨迹；且 Blizzard 偶尔会事后编辑旧补丁内容，普通用户无从感知。需要一个自动化系统：定时抓取两站补丁、格式化归档进 GitHub 仓库、把改动解析成结构化数据以支持"查士兵76子弹伤害历史"这类查询，并在出现新补丁或旧补丁被修改时通知用户。

## [S2] Design

### 数据获取（已实测验证）

- 英文站月份 URL：`https://overwatch.blizzard.com/en-us/news/patch-notes/live/{YYYY}/{MM}/`，2016-05 至今逐月齐全，纯服务端渲染；权威月份列表取自页面内嵌 JS 变量 `patchNotesDates.live`。
- 中文站月份 URL：`https://ow.blizzard.cn/news/patch-notes/live/{YYYY}/{MM}/`，仅 2025-02 至今；必须带尾斜杠；无补丁月份返回 404（作为"无补丁"信号）；月份只能枚举。
- 两站 HTML class 结构一致，解析器共用。补丁标识：EN 锚点 `id="patch-YYYY-MM-DD"`；CN 从标题 `《守望先锋》补丁说明——YYYY年M月D日` 提取日期。
- 抓取策略：requests.Session + 浏览器 UA，1 req/s 限速，失败 3 次指数退避重试。

### 数据模型

- patch id：`{site}-{YYYY-MM-DD}-{seq}`（seq 解决同天多补丁）。
- 每个补丁产出双文件：`data/archive/{site}/YYYY/MM/YYYY-MM-DD-seq.md`（人类可读）+ `data/patches/{site}/YYYY-MM-DD-seq.json`（结构化）。
- patch JSON：`{id, site, date, url, title, hash, sections[]}`；section 分 `hero_update`（heroes[]）与 `generic_update`。
- hero_update.heroes[]：`{slug, name_en, name_cn, perks[], abilities[]}`；ability：`{name_en, name_cn, slug, changes[]}`；change：`{text_en, text_cn, before, after, metric}`（before/after/metric 可空，原文必须保留）。
- perk：`{name_en, name_cn, status: added|removed|reworked|changed, lines_en[], lines_cn[]}`。
- 英雄轨迹 `data/heroes/{slug}.json`：`{slug, names{en,cn}, role, timeline:[{patch, date, site, ability, perk, change}]}`，每次入库由全部 patches 全量重建。
- 名称映射 `data/names.json`：键=英文原文 → `{cn, slug, role}`；技能名同表。未命中 → 自动 slugify + 写入 unknown_name 告警（不失败）。
- 数值提取：EN `(\w[\w ]+?) (increased|reduced|decreased|changed) from (\d+(?:\.\d+)?) to (\d+(?:\.\d+)?)`；CN `([\u4e00-\u9fff]+)从(\d+(?:\.\d+)?)点?(提高|缩短|降低|减少|增加)至(\d+(?:\.\d+)?)点?`。
- 2016 老格式（OW1 时代）解析不到结构时，降级存整段 `raw_text`。

### 变化检测与通知

- 每个 patch 的 `hash` = 规范化文本（剥空白）sha256，存 `data/manifest.json`。
- 每次运行：新 id → `new`；hash 变化 → `modified`（官方事后编辑），深度 diff 逐条写入 `data/changelog.jsonl`。
- 两种变化都触发：GitHub Issue（gh 创建，含变化摘要 + 源 URL）+ SMTP 邮件（合并 EN/CN 一封，best-effort，失败不导致 run 失败）。
- 无变化 → 零 commit、零通知。monitor 每 6 小时 cron + 可手动 dispatch。

### 查询

- GitHub Pages 静态站 `web/`（纯 HTML + 原生 JS，无构建链）：英雄列表页 + 英雄详情页（按技能/威能分组的时间线，EN 原文 / CN 翻译切换，每条链接源 URL）。
- CLI `tools/query.py`：`python tools/query.py <slug|中文名|英文名>`，支持 `--site --date` 查单补丁、`--json` 输出原始数据。

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
- [ ] T8: 三个 workflow yml + 接远程 + secrets + 端到端验证 — acceptance: GitHub dispatch monitor/pages/backfill 全部跑通，Pages 上线，收到真实 Issue + 邮件 (covers: S2-GitHub Actions; depends: T7)
