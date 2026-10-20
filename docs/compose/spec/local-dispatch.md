---
feature: local-dispatch
status: implemented
updated: 2026-10-19
---

# 本地工具触发归档（local-dispatch）

## 背景

`monitor-fast` 依赖 GitHub Actions 的 `schedule` 事件，而该事件是 best-effort：实测
`*/5` 的中位投递间隔约 28 分钟、最长可达 2 小时。本地的 `owpatch-tool` 每分钟抓一次
官方首页，能更快发现补丁；但它不负责归档（结构化、双语配对、英雄轨迹）。

因此新增一条**触发链路**：本地发现新补丁 → 调 GitHub `repository_dispatch` 让
`monitor-fast` **立即**跑一次常规扫描。归档仍由本仓库自行抓取官网，本地只提供
"该跑了"的信号与日期提示，不传输补丁内容。

## 事件契约

```http
POST https://api.github.com/repos/{owner}/{repo}/dispatches
Authorization: Bearer <token>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json

{
  "event_type": "owpatch-local-detect",
  "client_payload": {
    "source": "owpatch-tool",
    "tool_version": "1.4.0",
    "detected_at": "2026-10-19T02:10:00+08:00",
    "dates": ["2026-10-13"],
    "sites": ["en"],
    "reason": "new",
    "notify": false,
    "full": false
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `dates` | 是 | 本地看到的补丁日期（`YYYY-MM-DD`），用于跑后校验 |
| `sites` | 否 | `en` / `cn`；缺省表示两站都校验 |
| `reason` | 否 | `new` / `modified` / `manual`，仅用于日志 |
| `notify` | 否 | 默认 `false`：跳过 Issue/邮件（本地工具已推送） |
| `full` | 否 | 本地工具想全量扫描时的提示。工具侧 `--full` / `dispatch_target = "full"` 会**直接**调用 `monitor.yml` 的 `workflow_dispatch`，不再发 `repository_dispatch`（`monitor-fast` 固定 `--months 2` 增量窗口） |

响应：成功 `204 No Content`。

## 工作流行为（`.github/workflows/monitor-fast.yml`）

1. `repository_dispatch` 只接受 `owpatch-local-detect` 类型；
2. `Show dispatch payload` 把 `client_payload` 以 JSON 打到日志（便于追溯触发来源）；
3. 常规 `tools/run.py --data data --months 2`，抓取仍由本工作流完成；
4. **通知抑制**：`notify != true` 时不给 `--send-email`、不开更新 Issue
   （避免与本地推送重复）；`notify` 显式 `true` 时照常；
5. **入库校验**：`Verify dispatched dates landed in the archive` 检查
   `data/manifest.json` 是否含 `(site, date)`，缺失则 `exit 1` —— 解析坏掉不会静默变全绿；
6. 失败时沿用去重的"守望先锋监控异常"告警 Issue；
7. 提交数据后 `pages` 工作流通过 `workflow_run` 重建站点（约 2–5 分钟可看到结构化详情）。

## 令牌与权限

- 触发方（本地 `owpatch-tool`）持有 fine-grained PAT（或 classic PAT），仅授权本仓库：
  - `repository_dispatch`：**Contents: Read and write**（以 GitHub 文档与实测为准）；
  - 若走 `workflow_dispatch` 回退（例如事件未部署到默认分支）：**Actions: Read and write**。
- 令牌只保存在本地（`ui-config.toml`，POSIX 0600，或环境变量 `OWPATCH_GITHUB_TOKEN`），
  不写入本仓库、不进日志。
- `repository_dispatch` 只识别**默认分支**（`main`）上的工作流定义，改动合并后才生效。

## 去重与限流

- 本地侧冷却：默认 10 分钟内最多触发一次（`archive.dispatch_cooldown_minutes`）；
- 本工作流 `concurrency.group: monitor-fast` 串行执行，触发频繁时排队而非并发；
- 定时 `*/30` 与 `watchdog` 保留，作为触发失败/延迟时的兜底。

## 排障

| 现象 | 原因 / 处理 |
|---|---|
| `401 Unauthorized` | token 无效或过期 |
| `403 Forbidden` | token 权限不足（缺 Contents write / Actions write） |
| `404 Not Found` | 仓库名错，或工作流/事件类型未在默认分支上 |
| `422 Unprocessable Entity` | `event_type` 或 payload 不合法 |
| 触发了但归档无新补丁 | 看运行日志的 `Verify dispatched dates landed...` 与 `tools/run.py` 输出；可能是站点变体漂移或解析失败（会开告警 Issue） |
| 触发后站点 2–5 分钟才更新 | 正常：数据提交后由 `pages` 工作流重建 |
