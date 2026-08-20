"""tools/watchdog.py tests (offline, stub fetcher)."""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

from ow2_patch.fetch import CN_MONTH_URL, EN_INDEX_URL, FetchError, FetchResult

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(TOOLS))

import watchdog  # noqa: E402

EN_INDEX_NEW = (FIXTURES / "en_index.html").read_text(encoding="utf-8")  # anchor 2026-08-19
EN_INDEX_SAME = (FIXTURES / "en_index.html").read_text(encoding="utf-8").replace(
    "patch-2026-08-19", "patch-2026-08-14")
CN_2026_08 = (FIXTURES / "cn_2026_08.html").read_text(encoding="utf-8")
# the en_2026_08 fixture predates the 08-19 patch; prepend it so the probe's
# newest date is consistent with what the pipeline actually ingests
EN_2026_08 = (
    '<div class="PatchNotes-patch PatchNotes-live">'
    '<div class="anchor" id="patch-2026-08-19"></div>'
    '<div class="PatchNotes-labels"><div class="PatchNotes-date">August 19, 2026</div></div>'
    '<h3 class="PatchNotes-patchTitle">Overwatch Retail Patch Notes – August 19, 2026</h3>'
    '<div class="PatchNotes-section PatchNotes-section-generic_update">'
    '<h4 class="PatchNotes-sectionTitle">Bug Fixes</h4>'
    '<div class="PatchNotes-sectionDescription"><ul><li>Fixed an issue.</li></ul></div>'
    "</div></div>"
    + (FIXTURES / "en_2026_08.html").read_text(encoding="utf-8")
)


class StubFetcher:
    """Serves probe pages + pipeline months from fixtures."""

    def __init__(self, en_index: str = EN_INDEX_NEW, fail_get: bool = False):
        self.en_index = en_index
        self.fail_get = fail_get

    def get(self, url: str) -> str:
        if self.fail_get:
            raise FetchError("boom: connection reset")
        if url == EN_INDEX_URL:
            return self.en_index
        return CN_2026_08  # current CN month

    def en_month_list(self):
        return [(2026, 8)]

    def cn_month_list(self):
        return [(2026, 8)]

    def fetch_month(self, site, year, month):
        html = EN_2026_08 if site == "en" else CN_2026_08
        return FetchResult(html=html, url=f"https://x/{site}/{year}/{month}")


def _seed_manifest(data_dir: pathlib.Path, entries: dict) -> None:
    manifest = {"hash_schema": "v3", **entries}
    (data_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_probe_failure_exits_2(tmp_path, monkeypatch):
    monkeypatch.setattr(watchdog, "Fetcher", lambda: StubFetcher(fail_get=True))
    assert watchdog.main(["--data", str(tmp_path / "data")]) == 2


def test_fresh_archive_exits_0(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _seed_manifest(data_dir, {
        "en-2026-08-14-1": {"hash": "x", "site": "en", "date": "2026-08-14"},
        "cn-2026-08-15-1": {"hash": "x", "site": "cn", "date": "2026-08-15"},
    })
    monkeypatch.setattr(watchdog, "Fetcher", lambda: StubFetcher(en_index=EN_INDEX_SAME))
    assert watchdog.main(["--data", str(data_dir)]) == 0


def test_self_heal_ingests_missed_patch(tmp_path, monkeypatch):
    """Empty archive vs a live 08-19 patch -> stale -> full scan auto-ingests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _seed_manifest(data_dir, {})
    monkeypatch.setattr(watchdog, "Fetcher", lambda: StubFetcher())

    rc = watchdog.main(["--data", str(data_dir)])
    assert rc == 0

    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "en-2026-08-19-1" in manifest
    assert (data_dir / "patches" / "en" / "2026-08-19-1.json").exists()


@pytest.fixture(autouse=True)
def _cleanup_sys_path():
    yield
    if str(TOOLS) in sys.path:
        sys.path.remove(str(TOOLS))
