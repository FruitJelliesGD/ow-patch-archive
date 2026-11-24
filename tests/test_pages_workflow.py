"""Contract tests for `.github/workflows/pages.yml`.

Text assertions only: the repo does not depend on PyYAML (see
`tests/test_dispatch_workflow.py` for the same pattern). The contract that
matters here is the one that failed on GitHub: the deploy step looked up the
`github-pages` artifact, got nothing back (upload had already succeeded), and
turned the whole run red. These tests pin the fix — Node-24 action majors,
deploy retries that only fail after every attempt, and a queue instead of a
mid-deploy cancellation.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"

LEGACY_PINS = {
    "actions/checkout@v4",
    "actions/configure-pages@v5",
    "actions/upload-pages-artifact@v3",
    "actions/deploy-pages@v4",
}


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _code() -> str:
    """Workflow source with comments removed, so prose cannot satisfy a check."""
    lines = []
    for line in _text().splitlines():
        if line.lstrip().startswith("#"):
            continue
        lines.append(line.split(" #", 1)[0])
    return "\n".join(lines)


def _uses() -> list[str]:
    return re.findall(r"uses:\s*(\S+)", _code())


def test_triggers_are_unchanged():
    code = _code()
    assert "workflow_run:" in code
    assert "workflows: [monitor, monitor-fast, watchdog, ai-translate]" in code
    assert "types: [completed]" in code
    assert "branches: [main]" in code
    assert 'cron: "23 4 * * *"' in code
    assert "workflow_dispatch:" in code


def test_skips_deploy_when_monitor_failed():
    code = _code()
    assert "github.event_name != 'workflow_run'" in code
    assert "github.event.workflow_run.conclusion == 'success'" in code


def test_pages_actions_are_node24_majors():
    used = _uses()
    assert used.count("actions/checkout@v5") == 1
    assert "actions/configure-pages@v6" in used
    assert "actions/upload-pages-artifact@v5" in used
    assert used.count("actions/deploy-pages@v5") == 3
    assert [u for u in used if u in LEGACY_PINS] == []


def test_artifact_name_is_left_at_the_official_default():
    code = _code()
    # deploy-pages looks the artifact up by name; a custom `name:` on the
    # upload (or `artifact_name:` on the deploy) is a silent mismatch.
    assert "artifact_name:" not in code
    assert "name: github-pages" not in code


def test_uploads_the_staged_site():
    code = _code()
    assert "path: _site" in code
    assert "mkdir -p _site/data" in code
    assert "cp -r web/* _site/" in code
    assert "cp data/*.json _site/data/" in code
    assert "cp -r data/patches data/heroes data/ai_translations _site/data/" in code


def test_staging_does_not_ship_the_markdown_archive():
    assert "data/archive" not in _code()


def test_deploy_retries_transient_artifact_lookup_failures():
    code = _code()
    for attempt in (1, 2, 3):
        assert f"Deploy to GitHub Pages (attempt {attempt}/3)" in code
        assert f"id: deploy_{attempt}" in code
    assert code.count("uses: actions/deploy-pages@v5") == 3
    assert code.count("continue-on-error: true") == 3
    # Attempts 2 and 3 only run after the previous one failed, with a pause
    # so the artifact metadata has time to converge.
    assert "steps.deploy_1.outcome == 'failure'" in code
    assert "steps.deploy_2.outcome == 'failure'" in code
    assert "sleep 10" in code
    assert "sleep 20" in code


def test_only_a_total_deploy_failure_turns_the_run_red():
    code = _code()
    gate = (
        "steps.deploy_1.outcome == 'failure' && "
        "steps.deploy_2.outcome == 'failure' && "
        "steps.deploy_3.outcome == 'failure'"
    )
    assert gate in code
    assert "::error::" in code
    assert "exit 1" in code


def test_waits_for_the_artifact_before_deploying():
    # deploy-pages 曾在上传成功后几秒内报找不到 github-pages；先轮询确认产物
    # 可见，避免一次可恢复的抖动在运行页留下 failure 注解。
    code = _code()
    assert "Wait until the pages artifact is visible" in code
    assert "actions/runs/${GITHUB_RUN_ID}/artifacts" in code
    assert "grep -qx 'github-pages'" in code
    assert "::warning::" in code  # 超时只告警，不判红（后面还有部署重试）
    assert code.index("Wait until the pages artifact is visible") < code.index(
        "Deploy to GitHub Pages (attempt 1/3)"
    )


def test_does_not_pin_a_job_environment():
    # 仓库的 `github-pages` 环境配了自定义分支策略且不含 main，job 级
    # `environment:` 会让部署在起跑前就被拒（"Branch main is not allowed to
    # deploy to github-pages due to environment protection rules"）。不声明
    # environment 时 deploy-pages 仍会正常创建 Pages 部署。
    code = _code()
    assert "environment:" not in code
    assert "timeout-minutes: 15" in code


def test_runs_queue_instead_of_cancelling_an_inflight_deploy():
    code = _code()
    assert "group: pages" in code
    assert "cancel-in-progress: false" in code
    assert "cancel-in-progress: true" not in code


def test_permissions_stay_scoped_to_pages_deployment():
    code = _code()
    assert "contents: read" in code
    assert "actions: read" in code  # 轮询本次运行的 artifacts（只需读）
    assert "pages: write" in code
    assert "id-token: write" in code
    assert "contents: write" not in code
