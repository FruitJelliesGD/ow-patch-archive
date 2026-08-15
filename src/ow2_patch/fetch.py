"""Fetch Overwatch patch notes month pages (EN + CN) with rate limiting and retries."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date

import requests

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

EN_INDEX_URL = "https://overwatch.blizzard.com/en-us/news/patch-notes/"
EN_MONTH_URL = "https://overwatch.blizzard.com/en-us/news/patch-notes/live/{y}/{m}"
CN_MONTH_URL = "https://ow.blizzard.cn/news/patch-notes/live/{y}/{m}/"
CN_FIRST_MONTH = (2025, 2)  # 国服回归后才有补丁页，更早月份 404

# 页面内嵌 JS 变量，形如: patchNotesDates = {live:["2026-08","2026-07",...], ptr:[...], ...}
_PATCH_NOTES_DATES_RE = re.compile(r"patchNotesDates\s*=\s*(\{.*?\})\s*;", re.S)
_MONTH_ITEM_RE = re.compile(r'"(?P<ym>\d{4}-\d{2})"')


@dataclass(frozen=True)
class FetchResult:
    html: str
    url: str


class FetchError(RuntimeError):
    pass


class Fetcher:
    """Fetches month pages for both sites. One request per second, bounded retries."""

    def __init__(self, rate: float = 1.0, retries: int = 3, timeout: float = 30.0):
        self.rate = rate
        self.retries = retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = BROWSER_UA
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.rate:
            time.sleep(self.rate - elapsed)
        self._last_request = time.monotonic()

    def get(self, url: str) -> str:
        self._throttle()
        last_err: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 404:
                    raise FetchError(f"404: {url}")
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or resp.encoding
                return resp.text
            except requests.RequestException as exc:
                last_err = exc
                if attempt < self.retries - 1:
                    time.sleep(2 ** attempt)
        raise FetchError(f"fetch failed after {self.retries} tries: {url}: {last_err}")

    def en_month_list(self) -> list[tuple[int, int]]:
        """Authoritative month list from the embedded patchNotesDates JS variable."""
        html = self.get(EN_INDEX_URL)
        match = _PATCH_NOTES_DATES_RE.search(html)
        if not match:
            raise FetchError("patchNotesDates not found on EN index page")
        months = [_parse_ym(m) for m in _MONTH_ITEM_RE.findall(match.group(1))]
        return sorted({m for m in months if m})

    def cn_month_list(self) -> list[tuple[int, int]]:
        """Enumerate 2025-02 .. current month; 404 means no patches that month."""
        months: list[tuple[int, int]] = []
        y, m = CN_FIRST_MONTH
        today = date.today()
        while (y, m) <= (today.year, today.month):
            months.append((y, m))
            m += 1
            if m > 12:
                m = 1
                y += 1
        return months

    def fetch_month(self, site: str, year: int, month: int) -> FetchResult:
        mm = f"{month:02d}"
        if site == "en":
            url = EN_MONTH_URL.format(y=year, m=mm)
        elif site == "cn":
            url = CN_MONTH_URL.format(y=year, m=mm)
        else:
            raise ValueError(f"unknown site: {site}")
        return FetchResult(html=self.get(url), url=url)


def _parse_ym(value: str) -> tuple[int, int] | None:
    try:
        y, m = value.split("-")
        return int(y), int(m)
    except ValueError:
        return None
