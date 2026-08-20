"""Self-healing freshness watchdog: detects missed patches and auto-ingests them.

Usage:
  python tools/watchdog.py --data data [--notify-out watchdog-notify.json]
                           [--changed-out watchdog-changed.json] [--send-email]

Flow: probe the official sites' newest patch date (EN index anchor + CN current
month), compare with the archive's newest per site; when stale, run the full
pipeline (same shape as monitor.yml) to auto-ingest the missed patch(es), then
re-check that the gap is closed.

Exit codes:
  0  fresh, or stale but successfully self-healed (data changed; workflow commits)
  1  the self-heal pipeline itself failed (--fail-on-error path)
  2  probe failed, or the self-heal did not close the gap (workflow opens alert Issue)
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from ow2_patch.diff import load_manifest
from ow2_patch.fetch import Fetcher
from ow2_patch.freshness import (
    archive_newest_date,
    is_stale,
    newest_cn_patch_date,
    newest_en_patch_date,
)
from run import run_pipeline_cli

DEFAULT_DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OW patch freshness watchdog (self-healing)")
    parser.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA)
    parser.add_argument("--notify-out", type=pathlib.Path, default=None,
                        help="write notification JSON here when real changes are found")
    parser.add_argument("--changed-out", type=pathlib.Path, default=None,
                        help="write a marker file here when any data was persisted")
    parser.add_argument("--send-email", action="store_true")
    args = parser.parse_args(argv)

    fetch = Fetcher()
    try:
        probes = {"en": newest_en_patch_date(fetch), "cn": newest_cn_patch_date(fetch)}
    except Exception as exc:
        print(f"ERROR: freshness probe failed: {exc}")
        return 2

    manifest = load_manifest(args.data)
    archived = {s: archive_newest_date(manifest, s) for s in ("en", "cn")}
    stale_sites = [s for s in ("en", "cn") if is_stale(probes[s], archived[s])]

    for s in ("en", "cn"):
        flag = "  STALE" if s in stale_sites else ""
        print(f"{s} site={probes[s] or '-'} archive={archived[s] or '-'}{flag}")

    if not stale_sites:
        print("archive is fresh; nothing to do")
        return 0

    print(f"stale sites: {', '.join(stale_sites)}; running full scan to self-heal")
    rc = run_pipeline_cli(args.data, changed_out=args.changed_out,
                          notify_out=args.notify_out, send_email=args.send_email,
                          fail_on_error=True, fetch=fetch)
    if rc:
        return rc

    # verify the self-heal actually closed the gap (a parse breakage would not)
    manifest = load_manifest(args.data)
    still_stale = [s for s in stale_sites if is_stale(probes[s], archive_newest_date(manifest, s))]
    if still_stale:
        print(f"ERROR: archive still stale for {', '.join(still_stale)} after self-heal scan")
        return 2
    print("self-heal verified: archive now matches the sites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
