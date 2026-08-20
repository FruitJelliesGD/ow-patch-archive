---
feature: monitor-hardening
status: delivered
updated: 2026-08-20
branch: feat/monitor-hardening
commits: 7ad272a..e6939d7
---

# 监控加固:失败可见化 + 自愈看门狗 + 频率现实化

## Report

**What was built** — 三支柱加固,解决 08-19 补丁漏检的根因。(1) **失败可见化**:`RunResult.fetch_errors` 记录非 404 抓取失败,`tools/run.py` 抽出 `emit()`/`run_pipeline_cli()` 并新增 `--fail-on-error`(有抓取错误时退出 1、不写标记),`monitor`/`monitor-fast`/`watchdog` 三个工作流在失败时打开**去重的告警 Issue**(共享标题"守望先锋监控异常",`gh issue list` 探测 + `--limit 100` 防刷屏)——"监控坏了"不再表现为全绿静默。(2) **自愈看门狗**:新增 `src/ow2_patch/freshness.py`(EN 首页锚点探测、CN 当前月探测带 ≤2 月 404 回退、归档最新日期、stale 判定)+ `tools/watchdog.py` + `.github/workflows/watchdog.yml`(每日 05:13 UTC):探测站点最新补丁日期与归档比对,发现漏检自动跑全量扫描补录并**复检**;探测失败或自愈未闭合缺口退出 2 触发告警。部署后 08-19 补丁已由看门狗自动补录(无手动操作)。(3) **频率现实化**:`monitor-fast` cron `*/5` → `*/30`(schedule 事件 best-effort,实测中位数 28 分钟,见 S2 分析),README 同步修正。另修复一处既有缺陷:`fetch.py` 改为信任声明的 charset,仅在未声明时才用 `apparent_encoding`(chardet 曾把 UTF-8 页误判为 Windows-1252,产生乱码假 modified 事件)。

**Verification** — `pytest -q`(worktree,PYTHONPATH 前置 src):**132 passed**(基线 111 + 新增 21:test_fetch 3、test_freshness 7、test_run 6、test_watchdog 3、test_pipeline 扩展 2)。本地实站自愈验证:`python tools/watchdog.py --data data` → 探测 EN 2026-08-19 > 归档 08-14(CN 08-15 == 08-15)→ STALE → 全量扫描 143 个月 → **1 new(en-2026-08-19-1)、0 modified** → 复检通过 → 退出 0;数据已随分支提交(eb677ce),`patches_index.updated` 更新为 2026-08-19。编码修复实站验证:2016-05 月页无乱码。独立审查(general-2,7ad272a..e6939d7):spec 合规全部达标,无 critical/major,4 个 minor(文档措辞、去重健壮性、manifest 异常保护、交付记账)已修复并复测。

**Journey log** —
1. 本地自愈验证意外暴露既有编码缺陷:`apparent_encoding` 覆盖声明 charset,chardet 把 UTF-8 页误判为 Windows-1252 → 乱码 → 3 个旧补丁假 modified。修复为"声明优先"并重置被污染数据重跑,得到干净的 1 new 0 modified。
2. GitHub Actions 步骤的显式 `if:` 会**替换**隐式 `success()` 检查——失败步骤之后带 `if:` 的 commit 步骤仍会执行(数据照常提交且告警同时打开),比最初设计的"跳过提交"更好。
3. `*/5` 调度失败有官方依据:scheduled workflows 是 best-effort,高负载延迟甚至丢任务;结合 180 次运行的间隔统计(中位数 28.2 分钟、最大 111.8 分钟),`*/30` 才是与现实匹配的承诺。

## [S1] Problem

2026-08-19 官方英文站发布新补丁(Client Update),监控系统未检测、未提醒。诊断(见 `monitor-miss-diagnosis.md`)确认三个结构性缺陷:

1. **调度延迟**:`monitor-fast` 配置 `*/5`,GitHub Actions 实测中位数约 28 分钟、最大近 2 小时——"5 分钟发现新补丁"从未兑现,补丁在两次真实运行之间发布即漏检。
2. **静默失败**:pipeline 对非 404 抓取错误只打 WARN、退出码恒 0、工作流全绿;"监控坏了"与"没有新补丁"无法区分,也不会提醒任何人。
3. **无兜底**:没有机制对比"官方站点最新补丁 vs 归档最新日期",漏检只能靠人工发现。

用户要求:加固后**不再手动补录**,由系统自动发现并补上漏检的 08-19 补丁。

## [S2] Design

### 为什么 `*/5` 会失败(决策依据)

- GitHub 官方文档(`schedule` 事件,https://docs.github.com/en/actions/reference/events-that-trigger-workflows):
  *"The `schedule` event can be delayed during periods of high loads of GitHub Actions workflow runs. High load times include the start of every hour. If the load is sufficiently high enough, some queued jobs may be dropped."*
  即 schedule 是 best-effort:最短间隔 5 分钟,但**无投递保证**,高负载延迟、队列过载丢任务;且运行在默认分支最新提交上。
- 实证(本仓库 08-15~08-19 共 180 次运行,经 GitHub API 统计):间隔中位数 **28.2 分钟**、最大 111.8 分钟;理论 288 次/天,实际 28~51 次/天。
- 结论:`*/30` 与真实投递节奏一致;看门狗(每日)作最终兜底。

### 支柱 1 — 失败可见化

- `src/ow2_patch/pipeline.py`:`RunResult` 增加
  `fetch_errors: list[tuple[site, year, month, error]] = field(default_factory=list)`;
  抓取循环中非 404 异常在打 WARN 前追加记录(404 保持静默,它是"该月无补丁"的正常信号)。
- `tools/run.py`(最小重构,现有 CLI 行为不变):
  - `emit(result, changed_out, notify_out, send_email) -> int`:写入 changed 标记 / notify JSON / 发送邮件(现有逻辑抽出)。
  - `run_pipeline_cli(data_dir, months=None, sites=None, changed_out=None, notify_out=None, send_email=False, fail_on_error=False) -> int`:
    fetch → `run_pipeline` → `emit`;`fail_on_error` 且 `result.fetch_errors` 非空时逐条打印并返回 1。
  - `main()` 增加 `--fail-on-error` 参数。
- `.github/workflows/monitor.yml` / `monitor-fast.yml`:
  - run 命令加 `--fail-on-error`;
  - 新增去重告警步骤(见下),三个工作流共用标题前缀 `守望先锋监控异常`,保证全局最多一个 open 告警 Issue(持续故障不刷屏)。

```yaml
- name: Open alert issue (deduped)
  if: failure()
  env:
    GH_TOKEN: ${{ github.token }}
  run: |
    COUNT=$(gh issue list --state open --search '守望先锋监控异常 in:title' --limit 100 --json number --jq 'length' 2>/dev/null || echo 0)
    if [ "$COUNT" -gt 0 ]; then
      echo "open alert issue exists; skipping"
    else
      gh issue create --title "守望先锋监控异常" \
        --body "监控失败于 $(date -u +%Y-%m-%dT%H:%MZ)。日志: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
    fi
```

### 支柱 2 — 自愈看门狗(自动补录)

**`src/ow2_patch/freshness.py`(纯逻辑,可单测)**

- `EN_ANCHOR_RE = re.compile(r'id="patch-(\d{4}-\d{2}-\d{2})"')`
- `newest_en_patch_date(fetch: Fetcher) -> str`:抓 EN 首页(1 请求),取第一个锚点日期;缺失抛 `FetchError`。
  依据:EN 首页首个补丁锚点实测为 `patch-2026-08-19`(探测 2026-08-20 验证)。
- `newest_cn_patch_date(fetch: Fetcher, today: date | None = None) -> str`:
  抓当前月页 → `parse_patch_notes` → 取 max `patch.date`;404 回退至多 2 个月;窗口耗尽返回 `""`(CN 当月无补丁,非错误)。
- `archive_newest_date(manifest: dict, site: str) -> str`:manifest 中该 site 的 max `date`(跳过 `hash_schema` 键)。
- `is_stale(site_newest: str, archive_newest: str) -> bool`:字符串日期比较。

**`tools/watchdog.py`(CLI,复用 `from run import run_pipeline_cli`)**

参数:`--data --notify-out --changed-out --send-email`。流程:

1. 探测 EN+CN 最新日期;任一探测异常 → 打印 + 返回 **2**(触发告警步骤);
2. 读 manifest,逐 site 判定 stale;
3. 全部新鲜 → 打印摘要,返回 0;
4. 任一 stale → 跑全量 `run_pipeline_cli`(与 monitor.yml 同形,自动补录漏检补丁);返回非 0 则原样返回;
5. **复检**:重算归档最新日期,若仍 stale(自愈失败,如解析断裂)→ 返回 2;否则返回 0。

退出码语义:0 = 新鲜或自愈成功(工作流走 commit + 新补丁 Issue);1 = 自愈全量扫描失败(`--fail-on-error`,不写标记,触发告警);2 = 探测失败或自愈未闭合缺口(触发告警)。
边界:自愈已写数据但复检仍 stale 返回 2 时,commit 步骤带显式 `if:` 条件(覆盖隐式 success 检查)仍会执行——数据照常提交且告警同时打开,比"只告警不提交"更好;下次运行在已提交数据基础上继续。

**`.github/workflows/watchdog.yml`(新)**

- `on: schedule: [{cron: "13 5 * * *"}], workflow_dispatch:` —— 每日 05:13 UTC,紧跟 monitor 03:23 全量扫描之后,验证其成果并自愈;
- `permissions: contents: write, issues: write`;`concurrency: group: watchdog, cancel-in-progress: false`;
- 步骤:checkout → setup-python 3.12 → `pip install .` →
  `python tools/watchdog.py --data data --notify-out watchdog-notify.json --changed-out watchdog-changed.json --send-email`(SMTP env 同 monitor)→
  Commit(`if: hashFiles('watchdog-changed.json') != ''`)→ 新补丁 Issue(`if: hashFiles('watchdog-notify.json') != ''`)→ 去重告警步骤(`if: failure()`)。

### 支柱 3 — 频率现实化

- `.github/workflows/monitor-fast.yml` cron `*/5` → `*/30`。

### README

修正"每 5 分钟"表述为 `*/30` + 每日看门狗;文档化告警 Issue 与自愈行为;目录增加 `freshness.py` / `watchdog.py` / `watchdog.yml`。

## [S3] Out of Scope

- 同日新补丁(seq 增加):日期探测视为相等,不触发自愈;由 `*/30` 与每日全量扫描的哈希比较兜底(已知限制,README 注明)。
- 公开仓库 60 天无活动自动停用 scheduled workflow(官方行为):本次不做心跳/重启用自动化,仅 README 提醒。
- 本地/桌面端提醒、webhook 等新渠道:不做。
- 诊断文档 `monitor-miss-diagnosis.md` 的内容修订:不做(独立交付物)。

## Tasks

- [x] T1: 失败可见化 — `RunResult.fetch_errors`、run.py `emit`/`run_pipeline_cli`/`--fail-on-error`、monitor + monitor-fast 告警步骤 — acceptance: 非 404 抓取错误时 `--fail-on-error` 退出 1;无 flag 行为不变 (covers: S2 支柱1)
- [x] T2: 自愈看门狗 — `freshness.py` + `watchdog.py` + `watchdog.yml` — acceptance: 本地运行 watchdog 探测到 EN 2026-08-19 > 归档 08-14 → 自动全量扫描补录并退出 0;断网时退出 2 (covers: S2 支柱2)
- [x] T3: 频率现实化 — monitor-fast cron `*/30` + README 修正 — acceptance: workflow 文件 cron 为 `*/30`;README 无"每 5 分钟"错误表述 (covers: S2 支柱3)
- [x] T4: 测试与验证 — 新增 `tests/test_freshness.py`、`tests/test_run.py`,扩展 `tests/test_pipeline.py` + fixture;`pytest -q` 全绿;本地 watchdog 自愈补录 08-19 验证 — acceptance: 测试通过且 data/ 出现 `en-2026-08-19-1` (covers: S2; depends: T1, T2)
