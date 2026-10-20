"""Contract tests for the local-dispatch entrypoint in monitor-fast.yml.

Text assertions only: the repo does not depend on PyYAML, and the contract we
care about (event type, payload logging, notification suppression, post-run
verification) is visible in the workflow source.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "monitor-fast.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_declares_repository_dispatch_event_type():
    text = _text()
    assert "repository_dispatch:" in text
    assert "types: [owpatch-local-detect]" in text


def test_payload_is_logged_as_json():
    text = _text()
    assert "Show dispatch payload" in text
    assert "toJson(github.event.client_payload)" in text


def test_email_is_suppressed_for_dispatch_unless_notify_true():
    text = _text()
    assert "--send-email" in text
    assert "github.event_name != 'repository_dispatch'" in text
    assert "github.event.client_payload.notify" in text


def test_issue_is_suppressed_unless_notify_true():
    text = _text()
    assert "github.event.client_payload.notify == true" in text


def test_verification_step_checks_manifest_dates():
    text = _text()
    assert "Verify dispatched dates landed in the archive" in text
    assert "manifest.json" in text
    assert 'os.environ.get("DATES"' in text
    assert 'os.environ.get("SITES"' in text


def test_still_supports_schedule_and_manual_dispatch():
    text = _text()
    assert 'cron: "*/30 * * * *"' in text
    assert "workflow_dispatch:" in text


def test_web_assets_have_no_reference_to_removed_maps_dir():
    """`web/maps/` (73MB) was a duplicate of `web/assets/maps/`; nothing may point at it."""
    offenders = []
    for path in (ROOT / "web").rglob("*"):
        if path.suffix not in {".js", ".html", ".css"} or not path.is_file():
            continue
        if 'src="maps/' in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(path.relative_to(ROOT))
    assert offenders == []
