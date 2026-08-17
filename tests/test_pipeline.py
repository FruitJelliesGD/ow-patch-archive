"""Pipeline integration tests (offline, fixture-backed stub fetcher)."""

from __future__ import annotations

import json
import pathlib

from ow2_patch.diff import HASH_SCHEMA_VERSION
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

    # manifest + changelog (hash_schema key tracks the content-hash version)
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["hash_schema"] == HASH_SCHEMA_VERSION
    assert set(manifest) - {"hash_schema"} == {
        "en-2026-08-14-1", "en-2026-08-12-1", "cn-2026-08-15-1", "cn-2026-08-13-1"}
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


def test_pipeline_name_only_edit_is_not_modified(tmp_path):
    """Hero/ability name edits are hash-neutral (not in the text bag) and must
    not produce any event — the daily scan stays silent on spelling churn."""
    fetcher = StubFetcher()
    data_dir = tmp_path / "data"
    run_pipeline(data_dir, months=MONTHS, fetch=fetcher)

    edited = (FIXTURES / "en_2026_08.html").read_text(encoding="utf-8")
    edited = edited.replace('<h5 class="PatchNotesHeroUpdate-name">D.Mon</h5>',
                            '<h5 class="PatchNotesHeroUpdate-name">D. Mon</h5>')
    fetcher.pages[("en", 2026, 8)] = edited

    result = run_pipeline(data_dir, months=MONTHS, fetch=fetcher)
    assert result.events == []


def test_pipeline_legacy_chrome_drift_is_not_modified(tmp_path):
    """Schema v3: legacy raw_text that differs only in site template chrome
    must hash equal — the 2016-2020 archive is immune to chrome churn."""
    from ow2_patch.diff import ensure_hash_schema, patch_hash
    from ow2_patch.model import Patch, patch_to_dict
    from ow2_patch.parse import parse_patch_notes

    data_dir = tmp_path / "data"
    (data_dir / "patches" / "en").mkdir(parents=True)
    patch = parse_patch_notes(
        (FIXTURES / "en_2016_05.html").read_text(encoding="utf-8"), "en", url="https://x"
    )[0]
    data = patch_to_dict(patch)
    data["hash"] = "sha256:old"
    patch_file = data_dir / "patches" / "en" / "2016-05-27-1.json"
    patch_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    manifest = {patch.id: {"hash": "sha256:old", "site": "en", "date": data["date"]}}
    (data_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    ensure_hash_schema(data_dir, manifest)
    migrated = json.loads(patch_file.read_text(encoding="utf-8"))["hash"]

    # the same patch re-fetched with chrome leaked into the raw_text (the
    # 2026-08-16 page layout) must hash identically after cleaning
    with_chrome = Patch(id="en-2016-05-27-1", site="en", date="2016-05-27", url="https://x",
                        title=data["title"], seq=1,
                        raw_text=data["raw_text"] + " Top of post June Patch Notes June")
    assert patch_hash(with_chrome) == migrated


def test_cn_variant_drift_detection():
    from ow2_patch.model import HeroUpdate, Patch, Section
    from ow2_patch.pipeline import is_cn_variant_drift

    def cn_patch(names):
        return Patch(id="cn-2026-06-17-1", site="cn", date="2026-06-17", url="x", title="t",
                     seq=1, sections=[Section(type="hero_update", title="输出",
                                              heroes=[HeroUpdate(name_cn=n) for n in names])])

    assert is_cn_variant_drift([cn_patch(["士兵：76", "猎空", "安娜", "黑百合", "天使", "卢西奥"])]) is False
    assert is_cn_variant_drift([cn_patch(["Soldier: 76", "Tracer", "Ana", "Widowmaker", "Mercy", "Lúcio"])]) is True
    assert is_cn_variant_drift([]) is False
    assert is_cn_variant_drift([cn_patch(["D.Va"])]) is False  # too little signal
    assert is_cn_variant_drift([cn_patch(["D.Va", "士兵：76", "猎空", "安娜", "黑百合"])]) is False


def test_pipeline_skips_cn_variant_drift(tmp_path):
    """The English-named CN variant must be skipped entirely: no writes, no
    events, so the Chinese archive and the notifications stay clean."""
    import re

    fetcher = StubFetcher()
    data_dir = tmp_path / "data"

    # cn month served in the international variant: all hero name elements English
    cn_html = (FIXTURES / "cn_2026_08_12.html").read_text(encoding="utf-8")
    english_names = re.sub(r'(class="PatchNotesHeroUpdate-name">)[^<]*(<)',
                           r"\1Hero X\2", cn_html)
    fetcher.pages[("cn", 2026, 8)] = english_names

    result = run_pipeline(data_dir, months=MONTHS, fetch=fetcher)
    # only the 2 EN patches are processed; the CN month was skipped as drift
    assert len(result.events) == 2
    assert all(e.patch.site == "en" for e in result.events)
    assert not (data_dir / "patches" / "cn" / "2026-08-12-1.json").exists()





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
    """Real-data check: no ability hash slugs, cross-site merge, perk reclassification."""
    hero = json.loads((REAL_DATA / "heroes" / "soldier-76.json").read_text(encoding="utf-8"))
    for entry in hero["timeline"]:
        if entry.get("kind") == "ability":
            assert not (entry.get("ability_slug") or "").startswith("hero-"), entry.get("ability_slug")

    hpr = [e for e in hero["timeline"] if e.get("ability_slug") == "heavy-pulse-rifle"]
    cn_spellings = {e["ability_cn"] for e in hpr if e.get("ability_cn")}
    # canonical name plus the bracket-abbreviated spelling (脉冲步枪) both merge in
    assert "重脉冲步枪" in cn_spellings
    assert cn_spellings >= {"重脉冲步枪"}

    stim = [e for e in hero["timeline"]
            if e.get("ability_slug") == "stim-pack" or e.get("perk_slug") == "stim-pack"]
    assert any(e.get("ability_cn") == "强化药剂" or e.get("perk_cn") == "强化药剂" for e in stim)

    agility = [e for e in hero["timeline"] if e.get("perk_slug") == "agility-training"]
    assert agility, "Agility Training should be grouped as a perk"

    helix = [e for e in hero["timeline"] if e.get("ability_slug") == "helix-rockets"]
    assert {e["date"] for e in helix} >= {"2023-07-11", "2023-08-10"}
