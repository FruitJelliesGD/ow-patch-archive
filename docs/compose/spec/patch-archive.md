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

- `monitor.yml`：每日 cron 全量扫描（所有月份，捕获旧补丁被官方修改）+ dispatch；有变化则 commit+push → gh issue → SMTP 邮件（邮件失败不阻断 run）。Secrets：`SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/SMTP_TO`。权限 `contents: write, issues: write`。
- `monitor-fast.yml`：每 5 分钟 cron 快扫最近 2 个月（快速发现新补丁），逻辑与 monitor 相同、独立通知门控文件。注意：GitHub 调度可能延迟数分钟；私有仓库分钟额度消耗较快。
- `backfill.yml`：手动 dispatch 全量回填，一次性 commit（数据已在仓库，按年分批仅对首次回填有意义），不通知。
- `pages.yml`：push main + 每日 cron + dispatch → configure-pages → 拷贝 web/ + data/ 到 _site/ → deploy-pages。权限 `pages: write, id-token: write`。说明：monitor 的自动 commit 由 GITHUB_TOKEN 推送，按 GitHub 规则不触发同仓库 `on: push` 工作流，故 pages 用每日 cron 兜底刷新。
- `ci.yml`：push/PR 运行 pytest。

## [S3] Out of Scope

- 不存原始 HTML 快照（changelog 已记录文本 diff）。
- 不用 LLM 解析（规则解析 + names.json + 自动映射学习足够，CI 零成本、可复现）。

## 迭代二：时间浏览 + 跨站对齐（2026-08-15 增量）

### 补丁配对与时间索引（新增）

- EN/CN 补丁配对：CN 普遍滞后 EN 1 天（54 条中 36 条）。算法为**最大基数最小权二部图匹配**（不做精确日期预匹配，否则滞后集群会拆散配对），边权重 =（锚点日期差、标题日期差、EN 日期）；标题日期作第二信号（EN 2025-03-19 锚点实为 3/21 试玩，与 CN 03-22 配对）。结果：54/54 CN 全部配对。
- 产出 `data/patch_pairs.json`（配对关系）+ `data/patches_index.json`（按日期降序的逻辑补丁，含中英标题/URL/站点徽标，未配对补丁单语列出）。
- 生成时机：`pipeline.regenerate_all`（monitor 有新事件时）与 `tools/rebuild.py`（手动）均调用；纯离线、不动 manifest hash。

### 技能/威能中英映射自动学习（修复按条目查询错乱）

- 根因：names.json 技能表覆盖少 → 绝大多数 CN 技能名未命中 → 中文 hash-slug（全库 744 条），同一技能 EN/CN 分裂成两个分组；部分补丁把威能误放在技能列表（53 条）或把"名——威能 描述"合并进 general（35 条）。
- 修复：① `normalize.py` 重分类（威能状技能条目 → 威能、合并串拆分）；② `ability_map.py` 从配对补丁按英雄+位置对齐自动学习 EN↔CN 技能/威能名（含单复数变体折叠，如 Helix Rocket(s)）；③ `names.py` 解析优先级：names.json → ability_map → slugify，带 hero 上下文消歧。
- 结果：`hero-*` hash-slug 归零；`重型脉冲步枪` 等变体在重富化时规范化为 curated 名（`重脉冲步枪`）；英雄时间线按 canonical slug 跨站合并。

### 查询站重构（两种入口）

- `index.html` 改为**按时间浏览补丁**（年→月→列表，中英合并条目）；`heroes.html` 承接英雄列表；新增 `patch.html?id=&lang=` 补丁详情（语言切换、各站官方链接）；`hero.html` 分组改用 canonical slug。
- `web/app.js` 抽取公共 helpers，四页面共用；`tools/_smoke_web.js` 为无头冒烟测试（341 条目、双语切换、分组断言）。

## Tasks

- [x] T1: 抓取模块 `src/ow2_patch/fetch.py`（EN 月份枚举 + 单月抓取，含 2016 样例结构确认） — acceptance: 本地拉下 EN 某月 HTML 入 cache，2016 样例页真实结构已确认 (covers: S2-数据获取)
- [x] T2: 解析模块 `model.py` + `parse.py` — acceptance: `tests/test_parse.py` 全绿，EN/CN/2016 降级/同天多补丁样例全对 (covers: S2-数据模型; depends: T1)
- [x] T3: 名称映射 `data/names.json` 初版（OW2 全部英雄+技能）+ slug 生成 — acceptance: 样例英雄/技能全部命中映射，unknown_name 机制生效 (covers: S2-数据模型; depends: T2)
- [x] T4: 变化检测 `diff.py` + manifest + changelog — acceptance: `tests/test_diff.py` 全绿，人为改动 fixture 判为 modified (covers: S2-变化检测与通知; depends: T2)
- [x] T5: 通知 `notify.py`（Issue 正文 + SMTP 邮件） — acceptance: `--dry-run` 渲染的 Issue/邮件正文正确，SMTP 测试邮件收到 (covers: S2-变化检测与通知; depends: T4)
- [x] T6: 全量回填（EN 2016-05~今 + CN 2025-02~今）+ 英雄轨迹生成 — acceptance: 本地全量落库，patch 数与 patchNotesDates 一致，heroes/*.json 生成 (covers: S2-数据模型, S2-查询; depends: T5)
- [x] T7: 查询站 `web/` — acceptance: 本地 http.server 打开英雄详情正常展示时间线 (covers: S2-查询; depends: T6)
- [x] T8: 三个 workflow yml + 接远程 + secrets + 端到端验证 — acceptance: GitHub dispatch monitor/pages/backfill 全部跑通，Pages 上线，收到真实 Issue + 邮件 (covers: S2-GitHub Actions; depends: T7)
- [x] T9: 补丁配对 `pairing.py` + patch_pairs/patches_index — acceptance: 54 CN 全部配对、真实数据不变量测试通过 (covers: 迭代二-配对)
- [x] T10: 技能/威能映射学习 `ability_map.py` — acceptance: helix 单复数合并、重脉冲步枪/强化药剂解析正确 (covers: 迭代二-映射; depends: T9)
- [x] T11: `names.py` 扩展（map 加载、查表优先级、hero 上下文） — acceptance: test_names 增例全绿 (covers: 迭代二-映射; depends: T10)
- [x] T12: `normalize.py` 重分类 + build_hero_files canonical slug — acceptance: soldier-76 无 hash-slug、跨站合并、威能归类 (covers: 迭代二-映射; depends: T11)
- [x] T13: `regenerate_all` 接入 pipeline/rebuild — acceptance: 全量 pytest 43 项通过 (covers: 迭代二-配对; depends: T12)
- [x] T14: web 重构（时间浏览 / heroes / patch 详情 / 分组修复） — acceptance: 无头冒烟断言全过（341 条目、双语切换、无 hash 分组） (covers: 迭代二-查询站; depends: T9, T12)
- [x] T15: 合并推送 + pages 部署验证（迭代二收尾） — acceptance: main 更新、线上站点可用 (covers: 迭代二; depends: T14)

## 迭代三：词条级完整历史追溯（技能/武器/威能/英雄属性）

### 背景与目标（用户驱动）

用户判定现有追溯"不完善不合理"，要求基于已有数据结构升级为**技能/英雄/武器三维追溯**；核心原则"**出现即变更，所有词条可追溯历史**"——每个词条（技能/武器/威能/英雄属性）只要有记录就能查到完整历史；数值不追求精确推导（by-X% 不强推基准），任何条目绝不因提取不出数值而丢弃原文。展示=英雄页四类分组 + 数值轨迹序列；武器=词根+人工种子表。

### 数据与缺陷基线（审计实测）

- 数值提取只覆盖 `from X to Y`（EN 65%/CN 49%），漏 by-X%、to X (Up/Down from Y)、裸 reduced X%、meters-down-to、名词隔断 from-to（EN 138 条）
- general 占时间线 69%（8933 条）无结构化：health 685 / ultimate_cost 134 / move_speed 84 无法查询
- perk 名称泄漏进 general ~750 条（`Name - Power`/`——异能`）；bracket 前缀行 82 条（`[脉冲步枪]…`）应归属对应能力
- 武器维度缺失

### 设计决策

1. **hash 中立化（P0 关键）**：内容 hash 只含"补丁元数据 + 排序原文文本袋"，凡富化（names/slug/role）、归属移动（general→abilities/perks）、数值提取（before/by_pct/metric）一律不影响 hash → 升级零误报；`HASH_SCHEMA_VERSION=2` + `ensure_hash_schema` 一次性离线迁移（幂等）。**归属拆分必须保留原始整行**（perk 条目带 `raw_text`），否则存储文本袋与 fresh-parse 不一致会持续误报 modified（P1 修复）。
2. **数值提取 `extract.py`**：EN（from-to 名词隔断 / to X (Up/Down from Y) / by X% / 裸 X% / meters-down-to）+ CN（动词表补全含降至类、单位 点/秒/米/度/%）；`normalize_metric` 中英统一（damage/health/cooldown…），单位归一化；提取在重建层对已存文本离线重跑（parse 层委托同一逻辑）。
3. **归属 `attribution.py`**：bracket 前缀行 → 对应能力 changes（映射子串匹配+hero 校验，跨英雄拒绝）；perk 泄漏（`- Power`/`——异能`/前缀式）→ perk 条目（原文存 raw_text）；剩余按 hero_attr（health/ultimate_cost/move_speed/base_stat）或 other 结构化（含数值字段）；`fix_hash_slugs` 自愈历史 hash-slug。
4. **武器 `weapons.py` + data/weapons.json**：种子表 38 条 + 词根表（词边界匹配）+ exclude 黑名单（dragonblade 等大招）；ability_map 条目打 `kind: weapon|ability`（69 个武器）。
5. **数值轨迹 `values.py`**：按 (slug, metric) 的按日期 after 序列（同日期取最后），输出 hero JSON 顶层 `values`；perk 从 lines 提取数值；by_pct 无基准跳过。
6. **web**：hero 页按 武器/技能/威能/英雄属性 四维分组（DIM_ORDER），组头 values chip（`19 → 18`），属性徽标；`tools/_smoke_web.js` 断言。
7. **regenerate_all 串联**：reclassify → extract → re-enrich → pair → map（武器 kind）→ attribution → map v2 → hash 迁移 → heroes（含 values）；连续两次运行字节级幂等（updated 字段改为最新补丁日期派生）。

### 验收结果

- pytest 84 项全绿（新增 extract 20 用例、hash_migration、attribution、weapons、values + 既有回归）
- rebuild 幂等（快照对比 0 差异）；manifest `hash_schema=2`
- 数据审计：perk 泄漏 ~750→0（残留 2 条为 Stadium 物品名，正确留 general）；bracket 82→8 残余（解析失败留 general 原文）；hero_attr 1041 条结构化；武器 69；数值覆盖 54%→67%
- 词条历史：soldier-76 `heavy-pulse-rifle` 聚合全部出现记录（abilities 块 + `[脉冲步枪]` 归属 + EN/CN），`values["heavy-pulse-rifle:damage"]` 含 20→19→18 轨迹
- web smoke 全过（341 索引、5 维分区、values chip、无 hash 分组）
- 独立审查发现并修复：P1 hash 漂移（attribution 丢原文→45 补丁持续误报；修复=perk raw_text 保留整行+normalize 合并串同步+基线数据重建）；P2 词根误标（黑名单+词边界）、dev_note 入袋；P3 提取句式（CN 缩小/降至、EN up-from %、move speed 别名）与 perk 数值轨迹

## Tasks（迭代三）

- [x] T16: `extract.py` 数值提取升级 + metric/unit 归一化 + test_extract — acceptance: 20 表驱动用例全绿（含名词隔断/up-from/by%/down-to/CN 动词表）
- [x] T17: `diff.py` hash 新语义（排序原文袋）+ ensure_hash_schema 迁移 + test_hash_migration — acceptance: 推导字段/归属移动不改 hash、迁移幂等、fresh-parse 零误报
- [x] T18: model Change 扩展 + general dict 化 + 消费者适配 — acceptance: 全量 pytest 回归
- [x] T19: `attribution.py` 归属修复 + test_attribution — acceptance: bracket 归属、perk 泄漏归入且原文保留、hero_attr 分类、hash 中性
- [x] T20: `weapons.py` + 种子表 + ability_map kind + test_weapons — acceptance: 种子/词根/黑名单判定正确，69 武器标注
- [x] T21: `values.py` 轨迹序列 + 集成 + test_values — acceptance: after 链、同日期去重、by_pct 跳过
- [x] T22: regenerate_all 串联 + 迁移接入 + rebuild 幂等 — acceptance: 连续两次运行无 diff
- [x] T23: web 四类分组 + values chip + smoke 断言 — acceptance: 5 维分区、values、无 hash 分组
- [x] T24: 全量回归 + 数据审计复核 — acceptance: 84 测试、perk 泄漏归零、覆盖率 67%
- [ ] T25: 合并推送 + 线上验证（迭代三收尾） — acceptance: main 更新、ci/pages 绿、monitor 首轮零误报 (covers: 迭代三; depends: T24)
