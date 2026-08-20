---
feature: pages-auto-deploy
status: delivered
updated: 2026-08-20
branch: feat/pages-auto-deploy
commits: 372334c..463db44
---

# Pages 自动部署:监控数据入库后立即重建网站

## Report

**What was built** — `pages.yml` 新增 `workflow_run` 触发,监听 `monitor` / `monitor-fast` / `watchdog` 三个监控工作流完成(GITHUB_TOKEN 自动提交不触发 `on: push`,此前站点滞后最长约 18 小时);`deploy` job 以 `github.event.workflow_run.conclusion == 'success'` 过滤——监控失败(无新数据落库)不部署。保留 `push` / 每日 04:23 UTC schedule 兜底 / `workflow_dispatch` 三种既有触发。监控工作流完成并提交数据后,站点在约 30 分钟内自动重建;README 补充"自动重建"说明。

**Verification** — PyYAML `safe_load` 解析通过:triggers = push/schedule/workflow_dispatch/workflow_run,`workflow_run.workflows = [monitor, monitor-fast, watchdog]`、`types = [completed]`,`deploy.if` 为结论过滤表达式。纯配置改动,无代码/测试变更。独立审查(general-3,372334c..463db44):spec 合规全部达标,正确性无缺陷(workflow_run 对 schedule 触发同样生效;结论过滤行为正确;无递归风险;checkout 拉取最新 main 含 bot 数据提交),无 critical/major/minor。合入 main 后的真实验证:workflow_run 触发的 pages 部署由 GitHub API 确认(见交付后操作)。

**Journey log** —
1. 根因是 GitHub 防递归规则:github-actions[bot] 的 GITHUB_TOKEN 提交不触发 `on: push`;文件原有注释已承认并依赖每日 04:23 UTC 兜底——本次用 `workflow_run`(专为此场景设计)补上"提交后立即重建"。
2. `workflow_run` 会对无变化的成功运行也触发部署(约 30 分钟一次),公开仓库免费分钟与 Pages 构建限制均远高于实际消耗,作为已知代价写入 spec。

## [S1] Problem

检测到中文站新补丁(`cn-2026-08-20-1`,提交 `372334c` 于 08-20T10:20Z)已自动入库 main,但 GitHub Pages 查询站迟迟不显示。原因:`pages.yml` 的 `on: push` 不响应 github-actions[bot] 的自动提交(GitHub 防递归规则——GITHUB_TOKEN 产生的 push 不触发 workflow),兜底仅每日 04:23 UTC 定时重建,站点滞后最长约 18 小时。

## [S2] Design

**唯一改动文件:`.github/workflows/pages.yml`**

- `on:` 新增 `workflow_run` 触发,监听三个监控工作流完成:

```yaml
on:
  push:
    branches: [main]
  workflow_run:
    workflows: [monitor, monitor-fast, watchdog]
    types: [completed]
  schedule:
    - cron: "23 4 * * *"   # 保留兜底
  workflow_dispatch:
```

- `deploy` job 加结论过滤——监控失败(`--fail-on-error` 退出非 0)时没有新数据落库,不部署:

```yaml
jobs:
  deploy:
    if: github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success'
```

- 行为:任一监控工作流完成(schedule/push/dispatch 触发均可)且成功 → pages 重建,checkout 拉取最新 main(含 bot 已推送的数据)→ 站点滞后 ≤ monitor-fast 节奏(~30 分钟)。
- 无递归风险:pages 只读仓库 + 部署,不产生提交;现有 `concurrency: group: pages, cancel-in-progress: true` 处理重叠运行。
- 保留 `push`(人工/PR 合并)、`schedule` 兜底、`workflow_dispatch`(手动)三种既有触发。
- 已知代价:monitor-fast 每次完成(约 30 分钟一次,含无变化运行)都会触发一次 pages 重建;公开仓库免费分钟可忽略,Pages 构建限制(约 10 次/小时)远高于实际约 2 次/小时。
- README:功能一节补充"自动重建"说明(workflow_run 触发、~30 分钟生效、失败不部署、每日兜底)。

## [S3] Out of Scope

- 改为"仅当数据实际变化才部署"的精确触发(如监控工作流提交后显式 `gh workflow run pages.yml`):会增加三处耦合与 `actions: write` 权限,收益低,不做。
- 站点内容/布局改动:不做。
- 本地渲染预览(`tools/serve.py`)改动:不做。

## Tasks

- [x] T1: 修改 `pages.yml` — 新增 `workflow_run`(三个监控工作流)+ `deploy` job conclusion 过滤 — acceptance: YAML 语法校验通过;`on.workflow_run.workflows` 含 monitor/monitor-fast/watchdog (covers: S2)
- [x] T2: README 补充"自动重建"说明 + 本 spec 文档 — acceptance: README 描述 workflow_run 触发与 ~30 分钟生效;spec 文档结构完整 (covers: S2)
- [x] T3: 验证与审查、合并推送 — YAML 校验;独立审查通过;合并 main 并推送;手动 dispatch pages 立即刷新站点;API 确认 workflow_run 触发的部署 (covers: S2; depends: T1, T2)
