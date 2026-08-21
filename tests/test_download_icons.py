"""tools/download_icons.py tests: ref collection, URL preference, naming, safety."""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import download_icons as di  # noqa: E402


def _write_patch(data_dir: pathlib.Path, site: str, fname: str, date: str, heroes: list) -> None:
    d = data_dir / "patches" / site
    d.mkdir(parents=True, exist_ok=True)
    (d / fname).write_text(
        json.dumps({"date": date, "sections": [{"heroes": heroes}]}, ensure_ascii=False),
        encoding="utf-8",
    )


def _hero(slug: str, icon: str, abilities: list | None = None) -> dict:
    return {"slug": slug, "icon": icon, "abilities": abilities or []}


def test_collect_prefers_netease_over_cloudfront(tmp_path):
    _write_patch(tmp_path, "en", "2026-08-14-1.json", "2026-08-14", [
        _hero("d-mon", "https://d15f34w2p8l1cc.cloudfront.net/overwatch/aa.png",
              [{"slug": "purr", "icon": "https://d15f34w2p8l1cc.cloudfront.net/overwatch/bb.png"}])])
    _write_patch(tmp_path, "cn", "2026-08-15-1.json", "2026-08-15", [
        _hero("d-mon", "https://ld5.res.netease.com/images/cc.png",
              [{"slug": "purr", "icon": "https://ld5.res.netease.com/images/dd.png"}])])
    refs = di.collect_icon_refs(tmp_path)
    assert refs[("hero", "d-mon")][0].startswith("https://ld5.res.netease.com")
    assert refs[("ability", "d-mon/purr")][0].startswith("https://ld5.res.netease.com")


def test_collect_takes_latest_date_within_same_site(tmp_path):
    _write_patch(tmp_path, "en", "2026-08-11-1.json", "2026-08-11",
                 [_hero("d-mon", "https://d15f34w2p8l1cc.cloudfront.net/overwatch/old.png")])
    _write_patch(tmp_path, "en", "2026-08-14-1.json", "2026-08-14",
                 [_hero("d-mon", "https://d15f34w2p8l1cc.cloudfront.net/overwatch/new.png")])
    refs = di.collect_icon_refs(tmp_path)
    assert refs[("hero", "d-mon")][0].endswith("new.png")


def test_dry_run_reports_missing_without_writing(tmp_path):
    _write_patch(tmp_path, "en", "2026-08-14-1.json", "2026-08-14",
                 [_hero("d-mon", "https://d15f34w2p8l1cc.cloudfront.net/overwatch/aa.png")])
    out = tmp_path / "out"
    assert di.download_icons(tmp_path, out, dry_run=True) == 1
    assert not out.exists()


def test_existing_files_are_skipped(tmp_path):
    _write_patch(tmp_path, "en", "2026-08-14-1.json", "2026-08-14",
                 [_hero("d-mon", "https://d15f34w2p8l1cc.cloudfront.net/overwatch/aa.png")])
    out = tmp_path / "out"
    (out / "heroes").mkdir(parents=True)
    (out / "heroes" / "d-mon.png").write_bytes(b"x")
    assert di.download_icons(tmp_path, out, dry_run=True) == 0


def test_fetch_rejects_non_https():
    with pytest.raises(ValueError):
        di._fetch("http://insecure.example/x.png")


def test_is_image_magic():
    assert di._is_image(b"\x89PNG\r\n\x1a\nrest")
    assert di._is_image(b"\xff\xd8\xffrest")
    assert di._is_image(b"RIFF\x00\x00\x00\x00WEBP")
    assert not di._is_image(b"<html>not an image</html>")


def test_collect_map_refs(tmp_path):
    d = tmp_path / "patches" / "en"
    d.mkdir(parents=True)
    (d / "2026-08-11-1.json").write_text(json.dumps({
        "id": "en-2026-08-11-1", "date": "2026-08-11",
        "sections": [{"maps": [
            {"map_name": None, "area": "Downtown",
             "before": "https://images.blz-contentstack.com/v3/1.Before.jpg",
             "after": "https://images.blz-contentstack.com/v3/1.After.jpg"},
        ]}],
    }), encoding="utf-8")
    refs = di.collect_icon_refs(tmp_path)
    assert refs[("map", "en-2026-08-11-1/0-before")][0].endswith("1.Before.jpg")
    assert refs[("map", "en-2026-08-11-1/0-after")][0].endswith("1.After.jpg")


def test_map_downloads_into_maps_dir(tmp_path, monkeypatch):
    d = tmp_path / "patches" / "en"
    d.mkdir(parents=True)
    (d / "2026-08-11-1.json").write_text(json.dumps({
        "id": "en-2026-08-11-1", "date": "2026-08-11",
        "sections": [{"maps": [
            {"area": "Downtown", "before": "https://x/1.Before.jpg",
             "after": "https://x/1.After.jpg"},
        ]}],
    }), encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(di, "_fetch", lambda url: b"\xff\xd8\xffjpeg")
    assert di.download_icons(tmp_path, out) == 2
    assert (out / "maps" / "en-2026-08-11-1" / "0-before.png").exists()
    assert (out / "maps" / "en-2026-08-11-1" / "0-after.png").exists()


def test_marker_only_written_when_new_icons(tmp_path, monkeypatch):
    _write_patch(tmp_path, "en", "2026-08-14-1.json", "2026-08-14",
                 [_hero("d-mon", "https://d15f34w2p8l1cc.cloudfront.net/overwatch/aa.png")])
    marker = tmp_path / "icons.json"
    monkeypatch.setattr(di, "_fetch", lambda url: b"\x89PNG\r\n\x1a\nfake")
    out = tmp_path / "out"

    di.download_icons(tmp_path, out, marker=marker)
    assert marker.exists()
    assert json.loads(marker.read_text(encoding="utf-8")) == {"icons": 1}

    marker.unlink()
    di.download_icons(tmp_path, out, marker=marker)  # nothing new -> no marker
    assert not marker.exists()


@pytest.fixture(autouse=True)
def _cleanup_sys_path():
    yield
    if str(TOOLS) in sys.path:
        sys.path.remove(str(TOOLS))
