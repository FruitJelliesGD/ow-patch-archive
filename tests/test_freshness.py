"""Freshness probe tests (offline, stub fetcher)."""

from __future__ import annotations

import pathlib
from datetime import date

import pytest

from ow2_patch.fetch import CN_MONTH_URL, EN_INDEX_URL, FetchError
from ow2_patch.freshness import (
    archive_newest_date,
    is_stale,
    newest_cn_patch_date,
    newest_en_patch_date,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

EN_INDEX_HTML = (FIXTURES / "en_index.html").read_text(encoding="utf-8")
CN_2026_08 = (FIXTURES / "cn_2026_08.html").read_text(encoding="utf-8")


class StubFetch:
    """Minimal Fetcher stand-in: get(url) -> html, with optional per-URL errors."""

    def __init__(self, pages: dict[str, str], errors: dict[str, Exception] | None = None):
        self.pages = pages
        self.errors = errors or {}

    def get(self, url: str) -> str:
        if url in self.errors:
            raise self.errors[url]
        return self.pages[url]


def cn_url(y: int, m: int) -> str:
    return CN_MONTH_URL.format(y=y, m=f"{m:02d}")


def test_en_probe_takes_first_anchor():
    fetch = StubFetch({EN_INDEX_URL: EN_INDEX_HTML})
    assert newest_en_patch_date(fetch) == "2026-08-19"


def test_en_probe_missing_anchor_raises():
    fetch = StubFetch({EN_INDEX_URL: "<html><body>no anchors here</body></html>"})
    with pytest.raises(FetchError):
        newest_en_patch_date(fetch)


def test_cn_probe_current_month():
    fetch = StubFetch({cn_url(2026, 8): CN_2026_08})
    assert newest_cn_patch_date(fetch, today=date(2026, 8, 20)) == "2026-08-15"


def test_cn_probe_backtracks_on_404():
    fetch = StubFetch(
        {cn_url(2026, 8): CN_2026_08},
        errors={cn_url(2026, 9): FetchError(f"404: {cn_url(2026, 9)}")},
    )
    assert newest_cn_patch_date(fetch, today=date(2026, 9, 15)) == "2026-08-15"


def test_cn_probe_empty_window_returns_empty():
    errors = {cn_url(2026, m): FetchError(f"404: x") for m in (12, 11, 10)}
    fetch = StubFetch({}, errors=errors)
    assert newest_cn_patch_date(fetch, today=date(2026, 12, 1)) == ""


def test_cn_probe_non_404_raises():
    fetch = StubFetch({}, errors={cn_url(2026, 8): FetchError("boom: timeout")})
    with pytest.raises(FetchError):
        newest_cn_patch_date(fetch, today=date(2026, 8, 20))


def test_archive_newest_date_skips_hash_schema_and_other_sites():
    manifest = {
        "hash_schema": "v3",
        "en-2026-08-14-1": {"site": "en", "date": "2026-08-14"},
        "en-2026-08-12-1": {"site": "en", "date": "2026-08-12"},
        "cn-2026-08-15-1": {"site": "cn", "date": "2026-08-15"},
    }
    assert archive_newest_date(manifest, "en") == "2026-08-14"
    assert archive_newest_date(manifest, "cn") == "2026-08-15"
    assert archive_newest_date({}, "en") == ""
    assert archive_newest_date({"hash_schema": "v3"}, "en") == ""


def test_is_stale():
    assert is_stale("2026-08-19", "2026-08-14") is True
    assert is_stale("2026-08-14", "2026-08-14") is False  # same date: not stale
    assert is_stale("2026-08-14", "2026-08-19") is False
    assert is_stale("", "2026-08-14") is False  # no site data: never stale
