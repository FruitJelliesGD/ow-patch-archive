"""Notification rendering tests."""

from __future__ import annotations

import pathlib

from ow2_patch.diff import ChangeEvent, DiffEntry
from ow2_patch.notify import build_notification, load_smtp_from_env
from ow2_patch.parse import parse_patch_notes

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load_patch(name: str, site: str):
    return parse_patch_notes(
        (FIXTURES / name).read_text(encoding="utf-8"), site, url=f"https://example/{name}"
    )[0]


def test_notification_new_and_modified(monkeypatch):
    en = load_patch("en_2026_08.html", "en")
    cn = load_patch("cn_2026_08.html", "cn")
    events = [
        ChangeEvent("new", en),
        ChangeEvent("modified", cn, diff_entries=[
            DiffEntry("sections[1].heroes[0].abilities[0].changes[0].after", 0.15, 0.04),
            DiffEntry("sections[1].heroes[0].abilities[0].changes[0].text_en",
                      "Cast Time reduced from 0.15 to 0.05 seconds.",
                      "Cast Time reduced from 0.15 to 0.04 seconds."),
        ]),
    ]
    n = build_notification(events)
    assert n.title == "守望先锋补丁更新: 1 新增 · 1 修改"
    assert "en-2026-08-14-1" in n.body_md
    assert "D.Mon (" in n.body_md  # hero summary with change count
    assert "[源链接](https://example/" in n.body_md
    assert "| `sections[1].heroes[0].abilities[0].changes[0].after` | 0.15 | 0.04 |" in n.body_md
    assert "新增" in n.email_text and "修改" in n.email_text


def test_notification_no_events():
    n = build_notification([])
    assert n.title == "守望先锋补丁更新: 0 新增 · 0 修改"
    assert "## 新增补丁" not in n.body_md


def test_smtp_env_loading(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert load_smtp_from_env() is None
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")
    monkeypatch.setenv("SMTP_TO", "a@b.c")
    cfg = load_smtp_from_env()
    assert cfg["host"] == "smtp.example.com"
    assert cfg["port"] == 587
