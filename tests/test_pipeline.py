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
    """Structured legacy patches exclude site chrome by construction: the same
    page re-fetched with different chrome parses to identical sections, so the
    hash (and therefore the change detector) never sees template churn."""
    from ow2_patch.diff import patch_hash
    from ow2_patch.parse import parse_patch_notes

    html = (FIXTURES / "en_2016_05.html").read_text(encoding="utf-8")
    base = parse_patch_notes(html, "en", url="https://x")[0]

    # realistic chrome drift: a Top-of-post button / pagination block added
    drifted = html.replace(
        "</div>", '<div class="PatchNotesTop"><blz-button>Top of post</blz-button></div></div>', 1)
    reparse = parse_patch_notes(drifted, "en", url="https://x")[0]
    assert reparse.raw_text is None
    assert patch_hash(reparse) == patch_hash(base)


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


def test_pipeline_force_rewrite_persists_all_without_changelog(tmp_path):
    """force_rewrite re-persists every parsed patch with a fresh manifest hash,
    produces no change events and no changelog entries, and is byte-idempotent."""
    fetcher = StubFetcher()
    data_dir = tmp_path / "data"

    result = run_pipeline(data_dir, months=MONTHS, fetch=fetcher, force_rewrite=True)
    assert result.events == []
    assert not (data_dir / "changelog.jsonl").exists()

    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) - {"hash_schema"} == {
        "en-2026-08-14-1", "en-2026-08-12-1", "cn-2026-08-15-1", "cn-2026-08-13-1"}
    assert all(meta["hash"].startswith("sha256:")
               for pid, meta in manifest.items() if pid != "hash_schema")

    before = (data_dir / "patches" / "en" / "2026-08-14-1.json").read_text(encoding="utf-8")
    run_pipeline(data_dir, months=MONTHS, fetch=fetcher, force_rewrite=True)
    after = (data_dir / "patches" / "en" / "2026-08-14-1.json").read_text(encoding="utf-8")
    assert before == after


def test_fetch_errors_recorded_non404(tmp_path):
    """A non-404 fetch failure is recorded on RunResult so --fail-on-error can
    surface it; 404 stays silent (it is the normal 'no patches that month')."""
    from ow2_patch.fetch import FetchError

    class RaisingFetcher(StubFetcher):
        def fetch_month(self, site, year, month):
            if site == "cn":
                raise FetchError("boom: connection reset")
            return super().fetch_month(site, year, month)

    result = run_pipeline(tmp_path / "data", months=MONTHS, fetch=RaisingFetcher())
    assert result.fetched_months == 1
    assert result.fetch_errors == [("cn", 2026, 8, "boom: connection reset")]
    assert [e.patch.site for e in result.events] == ["en", "en"]  # EN still processed


def test_fetch_404_is_not_recorded(tmp_path):
    from ow2_patch.fetch import FetchError

    class NotFoundFetcher(StubFetcher):
        def fetch_month(self, site, year, month):
            if site == "cn":
                raise FetchError("404: https://x/cn/2026/08")
            return super().fetch_month(site, year, month)

    result = run_pipeline(tmp_path / "data", months=MONTHS, fetch=NotFoundFetcher())
    assert result.fetch_errors == []
    assert result.fetched_months == 1


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
