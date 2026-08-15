# 守望先锋补丁说明监控与留档系统

用 GitHub Actions 定时抓取《守望先锋》英文/中文官网补丁说明，格式化归档进本仓库，
并生成**英雄改动轨迹数据 + 静态查询站**（例如查"士兵76 的子弹伤害历史"、
"某英雄的威能经历了哪些新增/移除/重做"）。检测到**新补丁**或**旧补丁被官方事后修改**时，
通过 GitHub Issue + 邮件提醒。

- 英文站：<https://overwatch.blizzard.com/en-us/news/patch-notes/>（归档范围 2016-05 至今）
- 中文站：<https://ow.blizzard.cn/news/patch-notes/>（归档范围 2025-02 至今，国服回归）

## 功能

- **自动轮询**：`monitor` 工作流每 6 小时扫描两站全部月份页（`workflow_dispatch` 可手动触发）。
- **内容级变化检测**：对每条补丁计算规范化哈希并与 `data/manifest.json` 比对——
  新增补丁 / 旧补丁内容被修改都会触发提交 + Issue + 邮件，并把变更明细写入 `data/changelog.jsonl`。
- **格式化归档**：`data/archive/{en,cn}/YYYY/MM/` 下是每个补丁的可读 Markdown；
  `data/patches/` 下是结构化 JSON；`data/heroes/{slug}.json` 是聚合后的英雄改动时间线。
- **查询站**：GitHub Pages 静态站，按英雄浏览技能/威能改动历史，中英双语对照。
- **CLI 查询**：`python tools/query.py 士兵76`。

## 目录结构

```
src/ow2_patch/       抓取/解析/名称映射/变化检测/通知/流水线
tools/run.py         流水线入口（CI 使用）
tools/query.py       CLI 查询工具
tools/rebuild.py     修改 data/names.json 后重富化存量数据
web/                 GitHub Pages 查询站
data/               归档数据（全部提交入库）
  archive/          补丁 Markdown 归档
  patches/          补丁结构化 JSON
  heroes/           英雄改动时间线
  manifest.json     内容哈希状态
  changelog.jsonl   官方事后编辑记录
  names.json        EN/CN 名称映射表（可人工补充）
.github/workflows/  monitor / backfill / pages / ci
```

## 部署步骤

1. **创建 GitHub 仓库**并推送本分支：
   ```bash
   git push -u origin feat/patch-archive
   ```
   （合并到 `main` 后，`monitor` 定时任务与 `pages` 部署即开始工作。）

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
python tools/run.py --data data --months 3           # 增量扫描最近 3 个月
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
