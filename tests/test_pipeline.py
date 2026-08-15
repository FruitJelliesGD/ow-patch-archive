"""Pipeline integration tests (offline, fixture-backed stub fetcher)."""

from __future__ import annotations

import json
import pathlib

from ow2_patch.fetch import FetchResult
from ow2_patch.pipeline import run_pipeline

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

MONTHS = [("en", 2026, 8), ("cn", 2026, 8)]


class StubFetcher:
    def __init__(self):
        self.pages = {
            ("en", 2026, 8): (FIXTURES / "en_2026_08.html").read_text(encoding="utf-8"),
            ("cn", 2026, 8): (FIXTURES / "cn_2026_08.html").read_text(encoding="utf-8"),
        }

    def fetch_month(self, site, year, month):
        return FetchResult(html=self.pages[(site, year, month)], url=f"https://x/{site}/{year}/{month}")


def read_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_pipeline_end_to_end(tmp_path):
    fetcher = StubFetcher()
    data_dir = tmp_path / "data"

    result = run_pipeline(data_dir, months=MONTHS, fetch=fetcher)
    assert result.fetched_months == 2
    assert len(result.events) == 4  # 2 en + 2 cn new patches

    # patch json + markdown archive written
    assert (data_dir / "patches" / "en" / "2026-08-14-1.json").exists()
    md = (data_dir / "archive" / "en" / "2026" / "08" / "2026-08-14-1.md").read_text(encoding="utf-8")
    assert "Overwatch Retail Patch Notes" in md
    assert "Surging Strike" in md

    # manifest + changelog
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"en-2026-08-14-1", "en-2026-08-12-1", "cn-2026-08-15-1", "cn-2026-08-13-1"}
    changelog = read_jsonl(data_dir / "changelog.jsonl")
    assert {e["kind"] for e in changelog} == {"new"}
    assert all(e["patch_id"] for e in changelog)

    # hero files rebuilt: D.Mon has ability timeline; Jetpack Cat resolved from CN name
    hero = json.loads((data_dir / "heroes" / "d-mon.json").read_text(encoding="utf-8"))
    assert hero["names"] == {"en": "D.Mon", "cn": "D.Mon"}
    ability_entries = [e for e in hero["timeline"] if e["kind"] == "ability"]
    assert any(e["ability_en"] == "Surging Strike" and e["before"] == 0.15 for e in ability_entries)
    assert any(e["site"] == "cn" and e["ability_cn"] == "突进刺击" for e in ability_entries)

    jc = json.loads((data_dir / "heroes" / "jetpack-cat.json").read_text(encoding="utf-8"))
    assert jc["names"]["cn"] == "飞天猫"

    index = json.loads((data_dir / "heroes_index.json").read_text(encoding="utf-8"))
    assert {h["slug"] for h in index["heroes"]} >= {"d-mon", "jetpack-cat"}


def test_pipeline_idempotent_no_events(tmp_path):
    fetcher = StubFetcher()
    data_dir = tmp_path / "data"
    run_pipeline(data_dir, months=MONTHS, fetch=fetcher)

    result = run_pipeline(data_dir, months=MONTHS, fetch=fetcher)
    assert result.events == []
    changelog = read_jsonl(data_dir / "changelog.jsonl")
    assert len(changelog) == 4  # unchanged since first run
    # no new writes
    assert not (data_dir / "patches" / "en" / "2026-08-14-1.json.1").exists()


def test_pipeline_detects_content_edit(tmp_path):
    fetcher = StubFetcher()
    data_dir = tmp_path / "data"
    run_pipeline(data_dir, months=MONTHS, fetch=fetcher)

    # simulate Blizzard editing the hotfix: change a number in the EN page
    edited = (FIXTURES / "en_2026_08.html").read_text(encoding="utf-8")
    edited = edited.replace("from 0.15 to 0.05", "from 0.15 to 0.04")
    fetcher.pages[("en", 2026, 8)] = edited

    result = run_pipeline(data_dir, months=MONTHS, fetch=fetcher)
    assert [e.kind for e in result.events] == ["modified"]
    assert result.events[0].patch.id == "en-2026-08-14-1"

    changelog = read_jsonl(data_dir / "changelog.jsonl")
    edited_entry = [e for e in changelog if e["kind"] == "modified"][-1]
    assert any(d["path"].endswith("after") for d in edited_entry["diff"])
    assert any(d["new"] == 0.04 for d in edited_entry["diff"])

    # stored patch updated and hero timeline reflects new value
    stored = json.loads((data_dir / "patches" / "en" / "2026-08-14-1.json").read_text(encoding="utf-8"))
    hero = json.loads((data_dir / "heroes" / "d-mon.json").read_text(encoding="utf-8"))
    assert any(e.get("after") == 0.04 for e in hero["timeline"])
    assert any(
        c["after"] == 0.04
        for s in stored["sections"] for h in s["heroes"] for a in h["abilities"] for c in a["changes"]
    )
    # the sibling patch file is untouched
    other = json.loads((data_dir / "patches" / "en" / "2026-08-12-1.json").read_text(encoding="utf-8"))
    assert other["sections"][1]["heroes"][0]["abilities"][0]["changes"][0]["after"] == 65.0


def test_unknown_names_recorded_not_fatal(tmp_path):
    fetcher = StubFetcher()
    # rename a hero in the EN page to something unknown
    edited = (FIXTURES / "en_2026_08.html").read_text(encoding="utf-8")
    edited = edited.replace('>D.Mon<', '>D.Unknown<', 1)
    fetcher.pages[("en", 2026, 8)] = edited

    data_dir = tmp_path / "data"
    result = run_pipeline(data_dir, months=MONTHS, fetch=fetcher)
    assert any(name == "D.Unknown" for name, _ in result.unknown_heroes)
    # hero still archived under an auto slug
    assert (data_dir / "heroes" / "d-unknown.json").exists()


REAL_DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def test_soldier76_timeline_acceptance():
    """Real-data check: no hash slugs, cross-site ability merge, perk reclassification."""
    hero = json.loads((REAL_DATA / "heroes" / "soldier-76.json").read_text(encoding="utf-8"))
    for entry in hero["timeline"]:
        slug = entry.get("ability_slug") or entry.get("perk_slug") or ""
        assert not slug.startswith("hero-"), slug

    hpr = [e for e in hero["timeline"] if e.get("ability_slug") == "heavy-pulse-rifle"]
    cn_spellings = {e["ability_cn"] for e in hpr if e.get("ability_cn")}
    assert cn_spellings == {"重脉冲步枪"}  # variant 重型脉冲步枪 canonicalized to curated name

    stim = [e for e in hero["timeline"]
            if e.get("ability_slug") == "stim-pack" or e.get("perk_slug") == "stim-pack"]
    assert any(e.get("ability_cn") == "强化药剂" or e.get("perk_cn") == "强化药剂" for e in stim)

    agility = [e for e in hero["timeline"] if e.get("perk_slug") == "agility-training"]
    assert agility, "Agility Training should be grouped as a perk"

    helix = [e for e in hero["timeline"] if e.get("ability_slug") == "helix-rockets"]
    assert {e["date"] for e in helix} >= {"2023-07-11", "2023-08-10"}
