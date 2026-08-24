"""Notification rendering (GitHub Issue body + plain-text email) and SMTP sending.

Pure rendering is tested offline; SMTP send is best-effort (a misconfigured or
unreachable mail server must never fail the pipeline run).
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone

from .diff import ChangeEvent

SITE_LABEL = {"en": "英文站", "cn": "中文站"}


@dataclass
class Notification:
    title: str
    body_md: str
    email_text: str


def build_notification(events: list[ChangeEvent]) -> Notification:
    # cosmetic modified patches (name/chrome-only) are archived but not notified
    new = [e for e in events if e.kind == "new"]
    modified = [e for e in events if e.kind == "modified" and not e.cosmetic]
    parts = [f"{len(new)} 新增", f"{len(modified)} 修改"]
    title = f"守望先锋补丁更新: {' · '.join(parts)}"
    body = [_render_header(), ""]
    if new:
        body += ["## 新增补丁", ""]
        for e in new:
            body += _render_new(e.patch)
    if modified:
        body += ["## 内容被官方修改的补丁", ""]
        for e in modified:
            body += _render_modified(e.patch, e.diff_entries)
    return Notification(title=title, body_md="\n".join(body), email_text=_render_email(title, new + modified))


def _render_header() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"# 守望先锋补丁监控更新\n\n**扫描时间**: {now}"


def _render_new(patch) -> list[str]:
    heroes = _hero_summary(patch)
    lines = [f"### {patch.id} · {patch.date} · {SITE_LABEL[patch.site]}", ""]
    lines += [f"**{patch.title}**", "", f"[源链接]({patch.url})", ""]
    if not patch.sections and not patch.raw_text:
        lines += ["> ⚠️ 解析内容为空（补丁页为混合格式或结构变更），已归档空桩，需人工检查补录", ""]
    if heroes:
        lines += [f"涉及英雄改动: {', '.join(heroes)}", ""]
    return lines


def _render_modified(patch, diff_entries: list) -> list[str]:
    lines = [f"### {patch.id} · {patch.date} · {SITE_LABEL[patch.site]}", ""]
    lines += [f"**{patch.title}**", "", f"[源链接]({patch.url})", ""]
    if diff_entries:
        lines += ["| 位置 | 旧值 | 新值 |", "|---|---|---|"]
        for d in diff_entries[:20]:
            lines.append(f"| `{d.path}` | {_fmt(d.old)} | {_fmt(d.new)} |")
        lines.append("")
    return lines


def _hero_summary(patch) -> list[str]:
    out: list[str] = []
    for section in patch.sections:
        for hero in section.heroes:
            name = hero.name_en or hero.name_cn or hero.slug
            count = len(hero.abilities) + len(hero.perks) + len(hero.general)
            if count:
                out.append(f"{name} ({count})")
    return out


def _fmt(value) -> str:
    if isinstance(value, str) and len(value) > 60:
        return value[:57] + "..."
    return json.dumps(value, ensure_ascii=False) if value is not None else "∅"


def _render_email(title: str, events: list[ChangeEvent]) -> str:
    lines = [title, "", "请在 GitHub 仓库查看完整详情与归档数据。", ""]
    for e in events:
        p = e.patch
        kind = "新增" if e.kind == "new" else "修改"
        lines.append(f"[{kind}] {SITE_LABEL[p.site]} {p.date}: {p.title}")
        lines.append(f"  {p.url}")
        if e.kind == "modified" and e.diff_entries:
            for d in e.diff_entries[:5]:
                lines.append(f"  - {d.path}: {_fmt(d.old)} -> {_fmt(d.new)}")
    return "\n".join(lines)


def load_smtp_from_env() -> dict | None:
    host = os.environ.get("SMTP_HOST")
    if not host:
        return None
    try:
        port = int(os.environ.get("SMTP_PORT") or "465")
    except ValueError:
        port = 465
    return {
        "host": host,
        "port": port,
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASS", ""),
        "to": os.environ.get("SMTP_TO", ""),
    }


def send_email(cfg: dict, subject: str, text: str) -> None:
    """Best-effort SMTP send; raises only on hard configuration errors."""
    if not cfg.get("to"):
        raise ValueError("SMTP_TO is not set")
    context = ssl.create_default_context()
    if cfg["port"] == 465:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=30) as smtp:
            _authenticate_and_send(smtp, cfg, subject, text)
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as smtp:
            smtp.starttls(context=context)
            _authenticate_and_send(smtp, cfg, subject, text)


def _authenticate_and_send(smtp, cfg: dict, subject: str, text: str) -> None:
    if cfg.get("user"):
        smtp.login(cfg["user"], cfg["password"])
    message = (
        f"From: {cfg.get('user') or 'noreply@example.com'}\r\n"
        f"To: {cfg['to']}\r\n"
        f"Subject: {subject}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        f"{text}"
    )
    smtp.sendmail(cfg.get("user") or "noreply@example.com", [cfg["to"]], message.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    import argparse
    import pathlib

    parser = argparse.ArgumentParser(description="OW patch notification tooling")
    sub = parser.add_subparsers(dest="command", required=True)

    render_p = sub.add_parser("render", help="Render notification from a changelog.jsonl (dry-run)")
    render_p.add_argument("changelog", type=pathlib.Path)
    render_p.add_argument("--last", type=int, default=10)

    send_p = sub.add_parser("send", help="Send email from a notification JSON file")
    send_p.add_argument("notification", type=pathlib.Path)

    args = parser.parse_args(argv)

    if args.command == "render":
        entries = [
            json.loads(line)
            for line in args.changelog.read_text(encoding="utf-8").splitlines()
        ][-args.last:]
        if not entries:
            print("(no entries)")
            return 0
        # changelog entries have no Patch objects; show a compact summary
        for e in entries:
            print(f"[{e['kind']}] {e['patch_id']} {e['title']} {e['url']}")
            for d in e.get("diff", [])[:5]:
                print(f"    {d['path']}: {d['old']!r} -> {d['new']!r}")
        return 0

    notification = json.loads(args.notification.read_text(encoding="utf-8"))
    cfg = load_smtp_from_env()
    if cfg is None:
        print("SMTP_HOST not set; skipping email")
        return 0
    send_email(cfg, notification["title"], notification["email_text"])
    print(f"email sent to {cfg['to']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
