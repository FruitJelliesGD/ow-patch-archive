"""CLI runner: fetch -> parse -> diff -> persist; optionally emit a notification file.

Usage:
  python tools/run.py --data data [--months N] [--notify-out notify.json]
                      [--send-email] [--sites en cn]

The notification JSON (title/body_md/email_text) is only written when the run found
changes, so its presence gates the commit + Issue + email steps in the workflow.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from ow2_patch.diff import ChangeEvent
from ow2_patch.fetch import Fetcher
from ow2_patch.notify import build_notification, load_smtp_from_env, send_email
from ow2_patch.pipeline import all_months, run_pipeline

DEFAULT_DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def recent_months(months: list[tuple[str, int, int]], count: int) -> list[tuple[str, int, int]]:
    """Keep only the last `count` distinct months across sites (today-count .. today)."""
    today = __import__("datetime").date.today()
    cutoff_y, cutoff_m = today.year, today.month
    for _ in range(count - 1):
        cutoff_m -= 1
        if cutoff_m == 0:
            cutoff_m = 12
            cutoff_y -= 1
    return [m for m in months if (m[1], m[2]) >= (cutoff_y, cutoff_m)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OW patch monitor pipeline runner")
    parser.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA)
    parser.add_argument("--months", type=int, default=None,
                        help="only scan the last N months (backfill uses all)")
    parser.add_argument("--sites", nargs="+", choices=["en", "cn"], default=None)
    parser.add_argument("--notify-out", type=pathlib.Path, default=None,
                        help="write notification JSON here when changes are found")
    parser.add_argument("--send-email", action="store_true")
    args = parser.parse_args(argv)

    fetch = Fetcher()
    months = all_months(fetch)
    if args.sites:
        months = [m for m in months if m[0] in args.sites]
    if args.months is not None:
        months = recent_months(months, args.months)

    result = run_pipeline(args.data, months=months, fetch=fetch)
    print(f"scanned {result.fetched_months} months, "
          f"{len(result.events)} changes ({sum(1 for e in result.events if e.kind == 'new')} new, "
          f"{sum(1 for e in result.events if e.kind == 'modified')} modified)")

    for name, site in result.unknown_heroes:
        print(f"WARN: unknown hero {name!r} ({site}) — add to data/names.json")
    for name, site in result.unknown_abilities:
        print(f"WARN: unknown ability {name!r} ({site}) — add to data/names.json")

    if not result.events:
        print("no changes; nothing to commit or notify")
        return 0

    notification = build_notification(result.events)
    if args.notify_out:
        args.notify_out.write_text(
            json.dumps({
                "title": notification.title,
                "body_md": notification.body_md,
                "email_text": notification.email_text,
            }, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"notification written to {args.notify_out}")

    if args.send_email:
        cfg = load_smtp_from_env()
        if cfg is None:
            print("SMTP_HOST not set; skipping email")
        else:
            try:
                send_email(cfg, notification.title, notification.email_text)
                print(f"email sent to {cfg['to']}")
            except Exception as exc:  # email must never fail the run
                print(f"WARN: email failed, skipped: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
