---
feature: pages-deploy-resilience
status: delivered
updated: 2026-11-24
branch: main
---

# Pages 部署加固：产物查找瞬断重试 + 串行排队 + Actions 升级

## Report

**What was built** — `.github/workflows/pages.yml` 四处改动，解决 `deploy` 步骤长期偶发变红（2026-11-17 起 300 次运行中 8 次失败）：

1. **官方 Pages Actions 升级到 Node 24 世代**：`checkout@v4→v5`、`configure-pages@v5→v6`、`upload-pages-artifact@v3→v5`（内部改用 `upload-artifact@v7`）、`deploy-pages@v4→v5`（v5 增加部署状态轮询的退避与抖动）。旧版本被 GitHub 强制跑在 Node 24 上，运行注解每次都警告 Node 20 弃用。
2. **部署前先确认产物可见**：上传后用 `gh api` 轮询本次运行的 artifacts（30 次 × 2s），`github-pages` 出现才调用 `deploy-pages`；超时只 `::warning::`、不判红（后面还有重试）。抖动被吸收在部署之前，成功的运行不会留下 failure 注解。
3. **部署重试**：`deploy-pages` 改为 3 次尝试（间隔 10s / 20s），前两次失败只记日志，只有 3 次全部失败才 `::error::` + `exit 1`；3 个尝试都 `continue-on-error: true`。
4. **串行排队而非中途取消**：`concurrency.cancel-in-progress: true → false`。取消正在进行的 Pages 部署会让部署停在中间状态，历史上 6 次 `cancelled` 属于纯噪声。
5. 附带：权限增加 `actions: read`（轮询 artifacts 用）；`timeout-minutes: 15` 兜底；触发条件、`_site` 暂存范围（`data/patches` / `heroes` / `ai_translations`，不含 `data/archive`）、监控失败不部署的结论过滤全部保持不变。**不加** job 级 `environment:`：仓库的 `github-pages` 环境配了自定义分支策略且不含 `main`，声明 environment 会让部署在起跑前被拒（见 Journey log 4）。

**Verification** — `pytest -q`：**336 passed**（基线 324 + 新增 12 条 `tests/test_pages_workflow.py` 契约测试：触发条件、Action 主版本、产物默认名、暂存清单、先等产物可见、重试/门禁、无 job environment、并发策略、权限）；PyYAML 解析 `pages.yml` 通过；`node tools/_smoke_web.js` → `ALL WEB ASSERTIONS OK`。

线上：head `41a3ffc` 的 [ci run 45421473328](https://github.com/FruitJelliesGD/ow-patch-archive/actions/runs/45421473328)（`test` + `web`）与 [pages run 45421473592](https://github.com/FruitJelliesGD/ow-patch-archive/actions/runs/45421473592)（5 步全 success、第 1 次部署即成功、注解 0 条）均 success；站点 `https://fruitjelliesgd.github.io/ow-patch-archive/` 返回 200，`data/patches_index.json` 353 条。随后 head `56eab53` 的 pages 运行第 1 次部署又命中同款抖动、被重试救回（运行 success），但留下了 3 条 failure 注解——这正是追加"先等产物可见"步骤的原因（Journey log 5）。

**Journey log** —
1. 失败日志（需登录）不可得，改用公开的 run/job 元数据 + check-run 注解定位：`upload-pages-artifact` 步骤**成功**，紧接着的 `deploy-pages` 报 `No artifacts named "github-pages" were found for this workflow run.`，耗时仅 10–17 秒；同一天的失败运行是**串行**的（45210421984 → 45210477547 → 45211241395），排除了"两个部署并发"，指向 GitHub 侧产物元数据查询的瞬时故障/最终一致性。随后一次运行用同一份产物即可成功，说明重试是对症的。
2. 不重传产物：产物已在同一次运行里上传成功，且 `upload-pages-artifact` 不支持同名覆盖；重试部署（重新查询元数据）才是最小修复。
3. 重试做成 3 个显式步骤而不是 shell 循环：action 步骤无法在循环里调用，`continue-on-error` + `if: steps.deploy_N.outcome == 'failure'` 是 GitHub Actions 里唯一不需要第三方 action 的写法。
4. 首版照官方示例加了 job 级 `environment: github-pages`，首次线上运行 [run 45420969508](https://github.com/FruitJelliesGD/ow-patch-archive/actions/runs/45420969508) 3 秒即失败：`Branch "main" is not allowed to deploy to github-pages due to environment protection rules`（环境 `custom_branch_policies: true` 且列表不含 `main`）。删除 job 级 environment 即恢复：不带 environment 时 `deploy-pages` 仍能正常创建 Pages 部署（此前几个月一直如此）。
5. 重试虽能把运行救回，但被救回的那次尝试仍会留下 3 条 failure 级 check-run 注解（`continue-on-error` 只改步骤结论，不改 action 自己打的注解），运行页看起来仍像"有报错"。因此在部署前加产物可见性轮询：抖动在部署之前被吸收，运行保持 0 注解。

## [S1] Problem

`pages` 工作流部署步骤间歇性失败，示例 [run 45409701311](https://github.com/FruitJelliesGD/ow-patch-archive/actions/runs/45409701311)：

```
Fetching artifact metadata failed. Is githubstatus.com reporting issues with API requests, Pages, or Actions? ...
Error: No artifacts named "github-pages" were found for this workflow run.
    at getArtifactMetadata (.../deploy-pages/v4/src/internal/api-client.js:85:1)
```

失败分布（2026-11-17 起，共 8 次；最近 30 次运行里 6 次）：`43988555770`（11-17）、`44843634853`（11-21）、`45210421984` / `45210477547`（11-23 15:54，连续两次）、`45211241395`（11-23 15:58）、`45273441329`（11-23 21:48）、`45334874266`（11-24 05:39）、`45409701311`（11-24 14:02）。失败运行里 `Set up job`→`checkout`→`configure-pages`→`Stage site`→`upload-pages-artifact` 全部 success，只有 `deploy-pages` 失败；站点始终服务上一版，无数据损失。

放大因素：旧的 v3/v4 Actions 被强制在 Node 24 运行时（注解明确警告 Node 20 弃用）；部署步骤没有重试；`cancel-in-progress: true` 会取消进行中的部署。

## [S2] Design

唯一改动的行为文件是 `.github/workflows/pages.yml`：

- `concurrency.group: pages` + `cancel-in-progress: false` — 排队；GitHub 同一并发组只保留一个等待中的运行，不会堆积。
- 上传后用 `gh api repos/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID/artifacts` 轮询 `github-pages`（30 次 × 2s，需要 `actions: read`）；可见才进入部署，超时只 `::warning::` 并继续（重试兜底）。
- `deploy_1`（`continue-on-error: true`）→ 失败则 `sleep 10` → `deploy_2`（同）→ 失败则 `sleep 20` → `deploy_3`（同）→ 三者全失败才 `::error::` + `exit 1`。前两次失败在运行页显示为步骤告警，但整条运行仍为 success。
- 不声明 job 级 `environment:`（仓库 `github-pages` 环境的自定义分支策略不含 `main`，声明了会被拒），只加 `timeout-minutes: 15`。
- 产物名保持官方默认 `github-pages`（上传与部署两侧都不传自定义名），避免"上传成功、部署找不到"的名字不一致类故障。
- 契约测试（`tests/test_pages_workflow.py`）用纯文本断言锁住以上行为与触发条件，不引入 PyYAML 依赖。

## [S3] Out of Scope

- 不合并 `ci.yml` / `monitor*.yml` 里同类的 Node 20 弃用告警（是 warning，不影响运行结果；单独一次全仓库升级，避免把本次改动扩大成全局升级）。
- 不做"同一 commit 已部署则跳过"的去重（需要 deployments 读权限与新的竞态处理，收益低于风险）。
- 不改用 `upload-artifact` 手工构造 Pages 产物（官方要求单 tar，跨 action 会引入新的失败面）。
- 不处理 Doctrine 技能名学习缺陷（CN 2026-11-04 补丁只解析出 2 个技能条目，位置对齐把 `Eternal Scepter` 学成了 `迅影疾行`）；本次只在同步基线时修正 AI 镜像，根因另记。

## Tasks

- [x] T1: `pages.yml` 升级 4 个官方 Action 到 Node 24 主版本 — acceptance: 不再出现 v4/v3 旧版 (covers: S2)
- [x] T2: 部署前产物可见性轮询 + 3 次尝试 + 门禁 + timeout（不声明 job environment） — acceptance: 抖动被吸收在部署前；全失败才退出 1 (covers: S2)
- [x] T3: `concurrency.cancel-in-progress: false` — acceptance: 不再中途取消部署 (covers: S2)
- [x] T4: 新增 `tests/test_pages_workflow.py` — acceptance: `pytest -q` 全绿 (covers: S2)
- [x] T5: README 与本文档 — acceptance: 自动重建一节说明重试与排队 (covers: S2)
- [x] T6: 推送后线上验证 — acceptance: push 触发的 `ci` 与 `pages` 均 success (covers: S2; depends: T1, T2, T3, T4)
