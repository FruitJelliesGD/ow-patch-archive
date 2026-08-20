"""CLI runner: fetch -> parse -> diff -> persist; optionally emit a notification file.

Usage:
  python tools/run.py --data data [--months N] [--notify-out notify.json]
                      [--changed-out changed.json] [--send-email] [--sites en cn]
                      [--fail-on-error]

The changed marker is written whenever any data was persisted (new or modified,
including cosmetic-only edits) and gates the commit step; the notification JSON
is only written when the run found *real* content changes (cosmetic name/chrome
edits are archived but not notified) and gates the Issue/email steps.

--fail-on-error turns any non-404 fetch failure into a non-zero exit before any
marker is written, so CI workflows can surface a broken monitor (alert Issue)
instead of a green run that silently detected nothing.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from ow2_patch.diff import ChangeEvent
from ow2_patch.fetch import Fetcher
from ow2_patch.notify import build_notification, load_smtp_from_env, send_email
from ow2_patch.pipeline import RunResult, all_months, run_pipeline

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


def emit(result: RunResult, changed_out: pathlib.Path | None,
         notify_out: pathlib.Path | None, send_email: bool) -> int:
    """Print the scan summary and, when there are changes, write markers / notify."""
    real = [e for e in result.events if not (e.kind == "modified" and e.cosmetic)]
    cosmetic = len(result.events) - len(real)
    print(f"scanned {result.fetched_months} months, "
          f"{len(result.events)} changes ({sum(1 for e in result.events if e.kind == 'new')} new, "
          f"{sum(1 for e in result.events if e.kind == 'modified')} modified"
          f"{f', {cosmetic} cosmetic' if cosmetic else ''})")

    for name, site in result.unknown_heroes:
        print(f"WARN: unknown hero {name!r} ({site}) — add to data/names.json")
    for name, site in result.unknown_abilities:
        print(f"WARN: unknown ability {name!r} ({site}) — add to data/names.json")

    if not result.events:
        print("no changes; nothing to commit or notify")
        return 0

    if changed_out:
        changed_out.write_text("{}", encoding="utf-8")
        print(f"changed marker written to {changed_out}")

    if not real:
        print("only cosmetic changes; data archived but nothing to notify")
        return 0

    notification = build_notification(real)
    if notify_out:
        notify_out.write_text(
            json.dumps({
                "title": notification.title,
                "body_md": notification.body_md,
                "email_text": notification.email_text,
            }, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"notification written to {notify_out}")

    if send_email:
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


def run_pipeline_cli(
    data_dir: pathlib.Path,
    months: list[tuple[str, int, int]] | None = None,
    sites: list[str] | None = None,
    changed_out: pathlib.Path | None = None,
    notify_out: pathlib.Path | None = None,
    send_email: bool = False,
    fail_on_error: bool = False,
    fetch: Fetcher | None = None,
    force_rewrite: bool = False,
) -> int:
    """Fetch -> run_pipeline -> emit. Shared by tools/run.py and tools/watchdog.py.

    With fail_on_error, any non-404 fetch failure aborts before emit so CI can
    alert instead of committing partial results. force_rewrite persists every
    parsed patch (no change detection, no changelog) and skips emit — it is a
    one-time format-migration mode, never used by the scheduled workflows.
    """
    fetch = fetch or Fetcher()
    scan_months = months if months is not None else all_months(fetch)
    if sites:
        scan_months = [m for m in scan_months if m[0] in sites]
    result = run_pipeline(data_dir, months=scan_months, fetch=fetch,
                          force_rewrite=force_rewrite)
    if fail_on_error and result.fetch_errors:
        for site, year, month, err in result.fetch_errors:
            print(f"ERROR: fetch failed {site} {year}-{month:02d}: {err}")
        return 1
    if force_rewrite:
        print(f"force-rewrite done: {len(scan_months)} months scanned, "
              f"{result.fetched_months} fetched, {len(result.fetch_errors)} fetch errors")
        for name, site in result.unknown_heroes:
            print(f"WARN: unknown hero {name!r} ({site}) — add to data/names.json")
        for name, site in result.unknown_abilities:
            print(f"WARN: unknown ability {name!r} ({site}) — add to data/names.json")
        return 0
    return emit(result, changed_out, notify_out, send_email)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OW patch monitor pipeline runner")
    parser.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA)
    parser.add_argument("--months", type=int, default=None,
                        help="only scan the last N months (backfill uses all)")
    parser.add_argument("--sites", nargs="+", choices=["en", "cn"], default=None)
    parser.add_argument("--notify-out", type=pathlib.Path, default=None,
                        help="write notification JSON here when real changes are found")
    parser.add_argument("--changed-out", type=pathlib.Path, default=None,
                        help="write a marker file here when any data was persisted")
    parser.add_argument("--send-email", action="store_true")
    parser.add_argument("--fail-on-error", action="store_true",
                        help="exit non-zero when any non-404 fetch failed (CI alerting)")
    parser.add_argument("--force-rewrite", action="store_true",
                        help="re-persist every parsed patch without change detection "
                             "(one-time format migration; no changelog, no emit)")
    args = parser.parse_args(argv)

    fetch = Fetcher()
    months = all_months(fetch)
    if args.months is not None:
        months = recent_months(months, args.months)
    return run_pipeline_cli(
        args.data, months=months, sites=args.sites,
        changed_out=args.changed_out, notify_out=args.notify_out,
        send_email=args.send_email, fail_on_error=args.fail_on_error, fetch=fetch,
        force_rewrite=args.force_rewrite,
    )


if __name__ == "__main__":
    sys.exit(main())
