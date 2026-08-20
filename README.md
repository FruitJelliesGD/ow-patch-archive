# 守望先锋补丁说明监控与留档系统

用 GitHub Actions 定时抓取《守望先锋》英文/中文官网补丁说明，格式化归档进本仓库，
并生成**英雄改动轨迹数据 + 静态查询站**（例如查"士兵76 的子弹伤害历史"、
"某英雄的威能经历了哪些新增/移除/重做"）。检测到**新补丁**或**旧补丁被官方事后修改**时，
通过 GitHub Issue + 邮件提醒。

- 英文站：<https://overwatch.blizzard.com/en-us/news/patch-notes/>（归档范围 2016-05 至今）
- 中文站：<https://ow.blizzard.cn/news/patch-notes/>（归档范围 2025-02 至今，国服回归）

## 功能

- **两级自动轮询 + 自愈看门狗**：
  - `monitor-fast` 每 **30 分钟**快扫最近 2 个月页面，快速发现**新补丁**（GitHub Actions 的
    schedule 事件是 best-effort，`*/5` 实测中位数约 28 分钟才投递一次，故频率现实化为 `*/30`）；
  - `monitor` 每天 1 次全量扫描全部月份，捕获**旧补丁被官方修改**；
  - `watchdog` 每天 1 次**自愈检查**：探测官方站点最新补丁日期并与归档比对，发现漏检时
    自动跑全量扫描补录并补发提醒——**不需要手动补录**。
  （三个工作流均可通过 `workflow_dispatch` 手动触发。）
- **失败可见化**：任一工作流遇到非 404 抓取失败（`--fail-on-error`）会以非零码结束，
  并打开**去重的告警 Issue**（标题前缀"守望先锋监控异常"，三个工作流共享，最多一个 open），
  不再出现"全绿但什么都没检测"的静默故障。
- **内容级变化检测**：对每条补丁计算规范化哈希并与 `data/manifest.json` 比对——
  新增补丁 / 旧补丁内容被修改都会触发提交 + Issue + 邮件，并把变更明细写入 `data/changelog.jsonl`。
- **格式化归档**：`data/archive/{en,cn}/YYYY/MM/` 下是每个补丁的可读 Markdown；
  `data/patches/` 下是结构化 JSON；`data/heroes/{slug}.json` 是聚合后的英雄改动时间线。
- **查询站（GitHub Pages，两种入口）**：
  - **按时间浏览补丁**（首页）：年 → 月 → 补丁列表，同一逻辑补丁的英文/中文版本合并为一条，详情页可切换中英语言；
  - **词条检索**：直接搜索技能/武器/威能/英雄属性/英雄（中文名/英文名/别名/slug），每个词条独立成页，追溯全部更改记录（中英对照、数值 before→after、威能新增/移除/重做状态），并标注来源补丁曾被官方事后编辑（changelog 记录）。
  - **自动重建**：监控工作流（`monitor`/`monitor-fast`/`watchdog`）完成并提交数据后，`pages` 工作流
    通过 `workflow_run` 自动重建站点（约 30 分钟内生效；监控失败时不部署）；每日 04:23 UTC 定时重建兜底，
    也可 `workflow_dispatch` 手动触发。
- **跨站数据对齐**：英文与中文补丁自动配对（`data/patch_pairs.json`），技能/威能名称中英映射自动学习（`data/ability_map.json`），同一技能的改动历史跨站合并为一条，不再产生碎片化分组。
- **CLI 查询**：`python tools/query.py 士兵76`。

## 目录结构

```
src/ow2_patch/       抓取/解析/名称映射/配对/映射学习/变化检测/通知/流水线/新鲜度探测
tools/run.py         流水线入口（CI 使用）
tools/watchdog.py    自愈看门狗：探测官方站最新补丁日期，漏检时自动全量扫描补录
tools/query.py       CLI 查询工具
tools/rebuild.py     全量离线重生成（重分类/重富化/配对/映射/英雄轨迹）
web/                 GitHub Pages 查询站（时间浏览 + 词条检索）
data/               归档数据（全部提交入库）
  archive/          补丁 Markdown 归档
  patches/          补丁结构化 JSON
  heroes/           英雄改动时间线
  entries_index.json  词条检索索引（技能/武器/威能/英雄属性/英雄）
  official_edits.json 官方事后编辑记录（patch_id → 编辑事件列表）
  patches_index.json  按时间浏览索引（中英合并后的逻辑补丁）
  patch_pairs.json    EN/CN 补丁配对关系
  ability_map.json    技能/威能中英映射（自动学习，可再训练）
  manifest.json     内容哈希状态
  changelog.jsonl   官方事后编辑记录
  names.json        EN/CN 名称映射表（可人工补充）
.github/workflows/  monitor / monitor-fast / watchdog / backfill / pages / ci
```

## 部署步骤

1. **创建 GitHub 仓库**并推送本分支：
   ```bash
   git push -u origin feat/patch-archive
   ```
   （合并到 `main` 后，`monitor-fast`/`monitor` 定时任务与 `pages` 部署即开始工作。）

> **注意（私有仓库）**：私有仓库的 GitHub Actions 免费额度为 1000 分钟/月；
> 若仓库保持**公开**则 Actions 分钟数免费不限量。
> 另注意：GitHub 的 `schedule` 事件是 best-effort——高负载时会延迟甚至丢弃任务
> （官方文档：https://docs.github.com/en/actions/reference/events-that-trigger-workflows ），
> 本仓库实测 `*/5` 的 monitor-fast 实际投递间隔中位数约 28 分钟，故已现实化为 `*/30`；
> 漏检由每日 `watchdog` 自愈兜底，无需手动补录。

2. **启用 GitHub Pages**：仓库 Settings → Pages → Source 选 **GitHub Actions**。

3. **配置邮件通知（可选）**：仓库 Settings → Secrets and variables → Actions，添加：
   - `SMTP_HOST`（如 `smtp.qq.com`）、`SMTP_PORT`（465 走 SSL，或 587 STARTTLS）
   - `SMTP_USER` / `SMTP_PASS`（QQ/163 邮箱需使用**授权码**而非登录密码）
   - `SMTP_TO`（收件邮箱）
   
   未配置时自动跳过邮件，仅保留 GitHub Issue 通知（零配置）。

4. **验证**：Actions 页面手动运行 `monitor` / `backfill` / `pages`，检查 Issue 与邮件是否到达。

## 本地使用

```bash
python -m venv .venv && .\.venv\Scripts\activate     # Windows
pip install -e ".[dev]"

pytest -q                                            # 单元测试
python tools/run.py --data data --months 3           # 增量扫描最近 3 个月（两站）
python tools/watchdog.py --data data                 # 自愈看门狗：探测漏检并自动补录
python tools/query.py 士兵76                          # 查询英雄改动历史
python tools/query.py --site en --date 2026-08-12     # 查看单个补丁
python tools/serve.py                                 # 本地预览查询站 (http://127.0.0.1:8000)
```

## 维护

- **新英雄/技能名映射**：解析器对未知名自动生成 slug 并在运行日志输出
  `WARN: unknown hero/ability`；把名称补进 `data/names.json` 后运行
  `python tools/rebuild.py --data data` 即可重富化存量数据。
- **英文站老格式（OW1 时代）**：无现代结构的页面自动降级为整段原文 `raw_text`，内容不丢失。
- **中文站结构**：`ow.blizzard.cn` 的 HTML 存在未闭合标签，解析器按文本分片处理，不受影响。

## 已知边界

- 英文与中文站同一补丁的发布日期可能相差一天（如 EN 8/14 vs CN 8/15），两站独立归档，查询站按英雄聚合。
- Stadium 模式的外观物品块（"xxx Mask"）不进入英雄轨迹，但完整保留在归档 Markdown 中。
- 看门狗按"站点最新补丁日期 vs 归档最新日期"判断漏检；**同日新增的第二个补丁**（同日期不同 seq）
  日期相等不会触发自愈，由 `monitor-fast`/`monitor` 的哈希比较兜底。
- 公开仓库的 scheduled workflow 在**连续 60 天无仓库活动**时会自动停用（官方行为）；若长时间无提交，
  需在 Actions 页面重新启用。监控本身每天都会因数据变化/告警而活跃，通常不会触发。
