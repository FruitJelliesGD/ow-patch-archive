"""Freshness probes: compare the official sites' newest patch date with the archive.

Used by tools/watchdog.py to detect missed patches (staleness) and self-heal by
re-running the full pipeline. All functions are pure (given a Fetcher) so the
decision logic is unit-testable without the network.
"""

from __future__ import annotations

import re
from datetime import date as _date

from .fetch import CN_MONTH_URL, EN_INDEX_URL, FetchError, Fetcher
from .parse import parse_patch_notes

# the first anchor on the EN index page is the newest patch, e.g. id="patch-2026-08-19"
EN_ANCHOR_RE = re.compile(r'id="patch-(\d{4}-\d{2}-\d{2})"')

# how many months back to look on the CN site before declaring "no patch in window"
CN_BACKTRACK_MONTHS = 2


def newest_en_patch_date(fetch: Fetcher) -> str:
    """Newest patch date (YYYY-MM-DD) on the EN index page; raises FetchError."""
    html = fetch.get(EN_INDEX_URL)
    m = EN_ANCHOR_RE.search(html)
    if not m:
        raise FetchError(f"no patch anchor found on EN index: {EN_INDEX_URL}")
    return m.group(1)


def newest_cn_patch_date(fetch: Fetcher, today: _date | None = None) -> str:
    """Newest patch date (YYYY-MM-DD) on the CN site within a small backtrack window.

    Enumerates current .. current-CN_BACKTRACK_MONTHS; a 404 month means no patches
    that month. Returns "" when the whole window is empty (CN has no recent patches).
    """
    today = today or _date.today()
    for back in range(CN_BACKTRACK_MONTHS + 1):
        y, m = today.year, today.month
        for _ in range(back):
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        url = CN_MONTH_URL.format(y=y, m=f"{m:02d}")
        try:
            html = fetch.get(url)
        except FetchError as exc:
            if "404" in str(exc):
                continue
            raise
        patches = parse_patch_notes(html, "cn", url=url)
        if patches:
            return max(p.date for p in patches)
    return ""


def archive_newest_date(manifest: dict, site: str) -> str:
    """Newest archived patch date (YYYY-MM-DD) for a site, or "" if none."""
    newest = ""
    for patch_id, meta in manifest.items():
        if patch_id == "hash_schema" or not isinstance(meta, dict):
            continue
        if meta.get("site") != site:
            continue
        date = meta.get("date") or ""
        if date > newest:
            newest = date
    return newest


def is_stale(site_newest: str, archive_newest: str) -> bool:
    """True when the official site lists a patch newer than the archive."""
    return bool(site_newest) and site_newest > archive_newest
