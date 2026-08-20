"""tools/run.py runner tests (offline, stub fetcher).

tools/ is not a package; load run.py the same way tools/watchdog.py does at
runtime (its own directory on sys.path).
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from ow2_patch.fetch import FetchError, FetchResult

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(TOOLS))

import run  # noqa: E402

MONTHS = [("en", 2026, 8), ("cn", 2026, 8)]


class StubFetcher:
    def __init__(self, fail_cn: bool = False):
        self.fail_cn = fail_cn

    def fetch_month(self, site, year, month):
        if self.fail_cn and site == "cn":
            raise FetchError("boom: connection reset")  # non-404
        html = (FIXTURES / f"{site}_2026_08.html").read_text(encoding="utf-8")
        return FetchResult(html=html, url=f"https://x/{site}/{year}/{month}")


def test_fail_on_error_returns_1_and_skips_markers(tmp_path):
    data_dir = tmp_path / "data"
    changed = tmp_path / "changed.json"
    notify = tmp_path / "notify.json"

    rc = run.run_pipeline_cli(
        data_dir, months=MONTHS, fetch=StubFetcher(fail_cn=True),
        changed_out=changed, notify_out=notify, fail_on_error=True,
    )
    assert rc == 1
    assert not changed.exists(), "must not write markers on a failed scan"
    assert not notify.exists()


def test_without_flag_returns_0_and_emits(tmp_path):
    data_dir = tmp_path / "data"
    changed = tmp_path / "changed.json"
    notify = tmp_path / "notify.json"

    rc = run.run_pipeline_cli(
        data_dir, months=MONTHS, fetch=StubFetcher(fail_cn=True),
        changed_out=changed, notify_out=notify,
    )
    assert rc == 0
    assert changed.exists()  # EN patches were still archived
    assert notify.exists()  # real (non-cosmetic) changes


def test_clean_run_no_markers(tmp_path):
    data_dir = tmp_path / "data"
    changed = tmp_path / "changed.json"
    notify = tmp_path / "notify.json"

    rc = run.run_pipeline_cli(
        data_dir, months=MONTHS, fetch=StubFetcher(),
        changed_out=changed, notify_out=notify, fail_on_error=True,
    )
    assert rc == 0
    assert changed.exists()
    assert notify.exists()


def test_main_fail_on_error_flag(monkeypatch, tmp_path):
    class MainStub:
        def en_month_list(self):
            return [(2026, 8)]

        def cn_month_list(self):
            return [(2026, 8)]

        def fetch_month(self, site, year, month):
            raise FetchError(f"boom: {site} {year}-{month}")

    monkeypatch.setattr(run, "Fetcher", lambda: MainStub())
    assert run.main(["--data", str(tmp_path / "data"), "--fail-on-error"]) == 1
    assert run.main(["--data", str(tmp_path / "data")]) == 0


def test_recent_months():
    months = [("en", 2026, 8), ("en", 2026, 7), ("en", 2026, 6), ("en", 2026, 5)]
    kept = run.recent_months(months, 2)
    assert kept == [("en", 2026, 8), ("en", 2026, 7)]


@pytest.fixture(autouse=True)
def _cleanup_sys_path():
    yield
    if str(TOOLS) in sys.path:
        sys.path.remove(str(TOOLS))
