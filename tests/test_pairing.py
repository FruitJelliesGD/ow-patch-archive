"""Pairing algorithm tests (constructed scenarios + real-data invariants)."""

from __future__ import annotations

import json
import pathlib

from ow2_patch.pairing import (
    _parse_title_date,
    pair_patches,
    patch_meta_from_manifest,
)

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def make_patch(site: str, date: str, seq: int = 1, title: str | None = None) -> dict:
    return {
        "patch_id": f"{site}-{date}-{seq}",
        "site": site,
        "date": date,
        "title": title or f"{site} patch {date}",
        "url": f"https://x/{site}/{date}",
        "seq": seq,
        "title_date": _parse_title_date(title or f"{site} patch {date}", site),
    }


def test_exact_date_match():
    en = [make_patch("en", "2026-08-12", title="Overwatch Patch Notes – August 12, 2026")]
    cn = [make_patch("cn", "2026-08-12", title="《守望先锋》补丁说明——2026年8月12日")]
    result = pair_patches(en, cn)
    assert len(result.pairs) == 1
    assert result.pairs[0]["match"]["by"] == "anchor"
    assert result.pairs[0]["en"]["patch_id"] == "en-2026-08-12-1"
    assert result.pairs[0]["cn"]["patch_id"] == "cn-2026-08-12-1"


def test_one_day_lag_cluster_max_cardinality():
    # EN 26..29, CN 27..30: greedy diff0 would match CN27->EN27 leaving CN30 unmatched;
    # max-cardinality must match all four with CNx -> EN(x-1).
    en = [make_patch("en", f"2025-08-{d}") for d in (26, 27, 28, 29)]
    cn = [make_patch("cn", f"2025-08-{d}") for d in (27, 28, 29, 30)]
    result = pair_patches(en, cn)
    assert len(result.pairs) == 4
    matched = {p["cn"]["patch_id"]: p["en"]["date"] for p in result.pairs}
    assert matched["cn-2025-08-27-1"] == "2025-08-26"
    assert matched["cn-2025-08-30-1"] == "2025-08-29"
    assert result.unpaired_en == [] and result.unpaired_cn == []


def test_title_date_second_signal():
    # EN anchor 03-19 but title says March 21; CN 03-22 trial pairs via title diff 1
    en = [make_patch("en", "2025-03-19", title="Freja Hero Trial – March 21, 2025")]
    cn = [make_patch("cn", "2025-03-22", title="《守望先锋》补丁说明——2025年3月22日")]
    result = pair_patches(en, cn)
    assert len(result.pairs) == 1
    assert result.pairs[0]["match"]["by"] == "title"


def test_one_en_one_cn_no_orphan():
    en = [make_patch("en", "2025-03-18", title="Overwatch Patch Notes – March 18, 2025")]
    cn = [make_patch("cn", "2025-03-19", title="《守望先锋》补丁说明——2025年3月19日")]
    result = pair_patches(en, cn)
    assert len(result.pairs) == 1
    assert result.pairs[0]["match"]["date_diff"] == 1


def test_seq_only_matches_exact():
    en = [make_patch("en", "2025-06-27", 1), make_patch("en", "2025-06-27", 2)]
    cn = [make_patch("cn", "2025-06-27", 1)]
    result = pair_patches(en, cn)
    assert len(result.pairs) == 1
    assert result.pairs[0]["cn"]["patch_id"] == "cn-2025-06-27-1"
    assert result.pairs[0]["en"]["patch_id"] == "en-2025-06-27-1"
    assert "en-2025-06-27-2" in result.unpaired_en


def test_real_data_pairing_invariants():
    en, cn = patch_meta_from_manifest(DATA)
    assert len(en) == 343 and len(cn) == 56  # 342 EN + en-2026-08-20-1; + cn-2026-02-11-1
    result = pair_patches(en, cn)
    assert len(result.pairs) >= 45, f"only {len(result.pairs)} pairs"
    # every CN patch appears at most once across pairs + unpaired
    all_cn = [p["cn"]["patch_id"] for p in result.pairs] + result.unpaired_cn
    assert sorted(all_cn) == sorted(p["patch_id"] for p in cn)
    # pairs are deterministic
    again = pair_patches(en, cn)
    assert [p["en"]["patch_id"] for p in result.pairs] == [p["en"]["patch_id"] for p in again.pairs]


def test_patches_index_mode_pair(tmp_path):
    """Pair-level mode: either side non-standard wins (the CN April Fools title
    is tagged april_fools through its EN pair)."""
    from ow2_patch.pairing import PairResult, build_patches_index

    result = PairResult(pairs=[
        {"id": "p-2025-04-01-1", "date": "2025-04-01",
         "en": {"patch_id": "en-2025-04-01-1", "date": "2025-04-01", "seq": 1,
                "title": "Totally Normal Patch Notes for Totally Normalwatch - April 1, 2025",
                "url": "u"},
         "cn": {"patch_id": "cn-2025-04-01-1", "date": "2025-04-01", "seq": 1,
                "title": "《守望先锋》完全正常的“完全正常先锋”补丁说明——2025年4月1日",
                "url": "u"}},
        {"id": "p-2025-03-19-1", "date": "2025-03-19",
         "en": {"patch_id": "en-2025-03-19-1", "date": "2025-03-19", "seq": 1,
                "title": "Overwatch 2 Freja Hero Trial - March 21, 2025", "url": "u"},
         "cn": {"patch_id": "cn-2025-03-22-1", "date": "2025-03-22", "seq": 1,
                "title": "《守望先锋》英雄试玩：弗蕾娅——2025年3月22日", "url": "u"}},
    ])
    build_patches_index(tmp_path, result)
    index = json.loads((tmp_path / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert by_id["p-2025-04-01-1"]["mode"] == "april_fools"
    assert by_id["p-2025-03-19-1"]["mode"] == "hero_trial"


def test_real_patches_index_mode_invariants():
    """Real regenerated index: special patches carry their mode, standard ones
    stay standard (incl. unpaired entries)."""
    index = json.loads((DATA / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert by_id["en-2024-01-12-1"]["mode"] == "quick_play_hacked"  # unpaired
    assert by_id["en-2024-04-01-1"]["mode"] == "april_fools"
    assert by_id["p-2025-04-01-1"]["mode"] == "april_fools"  # pair, CN side non-keyword
    assert by_id["en-2024-12-17-1"]["mode"] == "experiment_6v6"
    assert by_id["en-2018-03-29-1"]["mode"] == "ptr"
    assert by_id["en-2022-10-04-1"]["mode"] == "announcement"
    assert by_id["p-2026-06-30-1"]["mode"] == "community_created"  # Community Crafted section
    assert by_id["p-2026-04-01-1"]["mode"] == "april_fools"  # Underwatch section, standard title
    assert by_id["p-2026-08-11-1"]["mode"] == "standard"
    assert by_id["en-2017-02-27-1"]["mode"] == "standard"  # uppercase variant
    assert all(p.get("mode") for p in index["patches"])


def test_real_patches_index_categories_invariants():
    """Content categories are display-only: content mentions tag the patch
    without reclassifying it (mode stays standard for mixed patches)."""
    index = json.loads((DATA / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert "quick_play_hacked" in by_id["p-2026-01-08-1"]["categories"]  # QP Hacked Assault block
    assert "quick_play_hacked" in by_id["p-2026-07-30-1"]["categories"]  # limited-time 6v6 dev note
    assert by_id["p-2026-01-08-1"]["mode"] == "standard"  # badge only, no reclassification
    assert "season" in by_id["p-2026-08-11-1"]["categories"]  # Reign of Talon - Season 4
    # OW1 competitive season launches are manual overrides (text lives in block
    # titles, outside the TITLE_FIRST season scope): S1 mode debut, S2, S3
    for ow1 in ("en-2016-06-28-1", "en-2016-09-02-1", "en-2016-11-15-1"):
        assert "season" in by_id[ow1]["categories"]
    # OW1 arcade/event seasons must NOT be tagged as 新赛季 (scope guard holds)
    assert "season" not in by_id["en-2021-09-07-1"]["categories"]  # Lockout Elimination S4
    assert "season" not in by_id["en-2021-12-16-1"]["categories"]  # No Limits S2
    assert sum("season" in p.get("categories", []) for p in index["patches"]) == 27
    # crossover: 13 rule-tagged (X-brand section/block titles) + 2 manual
    # overrides (Diablo, BlizzCon — description-only)
    for xid in ("en-2018-01-30-1", "en-2019-10-24-1", "en-2023-03-07-1",
                "en-2023-10-31-1", "en-2024-03-08-1", "en-2024-05-14-1",
                "en-2024-07-05-1", "en-2024-09-17-1", "en-2024-10-15-1",
                "en-2024-11-08-1", "p-2025-03-18-1", "p-2025-05-16-1",
                "p-2025-09-16-1", "en-2023-10-10-1", "en-2019-10-15-1"):
        assert "crossover" in by_id[xid]["categories"]
    # body-level noise must not badge: All Might skin bug, CN 联动 dev-note
    assert "crossover" not in by_id["en-2024-10-28-1"]["categories"]
    assert "crossover" not in by_id["p-2026-02-09-1"]["categories"]
    assert sum("crossover" in p.get("categories", []) for p in index["patches"]) == 15
    assert all(isinstance(p.get("categories"), list) for p in index["patches"])
    assert all("content_qp_hacked" not in p for p in index["patches"])


def test_patches_index_categories_union(tmp_path):
    """categories = union of both sides' content-detected categories in
    CATEGORY_ORDER; unpaired entries classify from their own content. Phrase
    placement respects the per-rule scope: new_hero matches a SECTION TITLE
    (body-level phrases no longer tag title-scoped keys)."""
    from ow2_patch.pairing import PairResult, build_patches_index

    data_dir = tmp_path / "data"
    _write_patch_json(data_dir, "en-2026-03-01-1",
                      [{"type": "generic_update", "title": "Season 5", "heroes": []},
                       {"type": "generic_update", "title": "Stadium Changes", "heroes": []}])
    _write_patch_json(data_dir, "cn-2026-03-02-1",
                      [{"type": "generic_update", "title": "新英雄无漾登场",
                        "blocks": [{"title": "", "body": "无漾技能一览", "dev": None}],
                        "heroes": []}])
    _write_patch_json(data_dir, "cn-2026-03-03-1",
                      [{"type": "generic_update", "title": "角斗领域改动", "heroes": []}])
    result = PairResult(
        pairs=[{
            "id": "p-2026-03-01-1", "date": "2026-03-01",
            "en": {"patch_id": "en-2026-03-01-1", "date": "2026-03-01", "seq": 1,
                   "title": "Overwatch Patch Notes", "url": "u"},
            "cn": {"patch_id": "cn-2026-03-02-1", "date": "2026-03-02", "seq": 1,
                   "title": "《守望先锋》补丁说明", "url": "u"},
        }],
        unpaired_cn=["cn-2026-03-03-1"],
    )
    build_patches_index(data_dir, result)
    index = json.loads((data_dir / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    # en=[season,stadium] ∪ cn=[new_hero] → CATEGORY_ORDER: season, new_hero, stadium
    assert by_id["p-2026-03-01-1"]["categories"] == ["season", "new_hero", "stadium"]
    assert by_id["cn-2026-03-03-1"]["categories"] == ["stadium"]


def test_patches_index_categories_scoped(tmp_path):
    """Body-level phrases no longer tag title-scoped keys; first-section and
    section-title placements do; the Stadium guard kills 'New Heroes Added'."""
    from ow2_patch.pairing import PairResult, build_patches_index

    data_dir = tmp_path / "data"
    # body-level season mention (bug-fix boilerplate) → no season badge
    _write_patch_json(data_dir, "en-2026-03-01-1",
                      [{"type": "generic_update", "title": "Bug Fixes",
                        "description": "Fixed Season 18 login rewards", "heroes": []}])
    # first-section season launch → season
    _write_patch_json(data_dir, "en-2026-03-02-1",
                      [{"type": "generic_update", "title": "WELCOME TO SEASON 5", "heroes": []}])
    # real intro section → new_hero
    _write_patch_json(data_dir, "en-2026-03-03-1",
                      [{"type": "hero_update", "title": "New Hero: Freja",
                        "heroes": [{"slug": "freja", "name_en": "Freja",
                                    "abilities": [{"name_en": "Railgun",
                                                   "changes": [{"text_en": "x"}]}]}]}])
    # Stadium-roster section title over plain-named stadium heroes → no new_hero
    _write_patch_json(data_dir, "en-2026-03-04-1",
                      [{"type": "hero_update", "title": "New Heroes Added",
                        "heroes": [{"slug": "doomfist", "name_en": "Doomfist",
                                    "stadium_items": [{"lines_en": ["Mask"]}]}]}])
    result = PairResult(pairs=[], unpaired_en=[
        "en-2026-03-01-1", "en-2026-03-02-1", "en-2026-03-03-1", "en-2026-03-04-1"])
    build_patches_index(data_dir, result)
    index = json.loads((data_dir / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert by_id["en-2026-03-01-1"]["categories"] == []
    assert by_id["en-2026-03-02-1"]["categories"] == ["season"]
    assert by_id["en-2026-03-03-1"]["categories"] == ["new_hero"]
    assert by_id["en-2026-03-04-1"]["categories"] == []


def test_structural_new_hero_signal(tmp_path):
    """new_hero fires for a hero's first-ever balance record when no earlier
    patch mentions its name; an earlier mention suppresses it; the signal is
    gated to the structured OW2 era; stadium-item-only blocks don't count."""
    from ow2_patch.pairing import PairResult, build_patches_index

    data_dir = tmp_path / "data"
    # earlier patch mentions Freja (no block) → suppresses the July intro
    _write_patch_json(data_dir, "en-2023-06-01-1",
                      [{"type": "generic_update", "title": "Roadmap",
                        "description": "Freja joins the roster next month", "heroes": []}])
    _write_patch_json(data_dir, "en-2023-07-01-1",
                      [{"type": "hero_update", "title": "Hero Updates",
                        "heroes": [{"slug": "freja", "name_en": "Freja",
                                    "abilities": [{"name_en": "Railgun",
                                                   "changes": [{"text_en": "x"}]}]}]}])
    # clean intro: first mention == first record
    _write_patch_json(data_dir, "en-2023-08-01-1",
                      [{"type": "hero_update", "title": "Hero Updates",
                        "heroes": [{"slug": "hazard", "name_en": "Hazard",
                                    "general": ["Added Hazard to the roster"]}]}])
    # pre-OW2-era intro → signal gated off
    _write_patch_json(data_dir, "en-2021-01-01-1",
                      [{"type": "hero_update", "title": "Hero Updates",
                        "heroes": [{"slug": "orisa", "name_en": "Orisa",
                                    "abilities": [{"name_en": "Protective Barrier",
                                                   "changes": [{"text_en": "x"}]}]}]}])
    # stadium-item-only block → not a hero introduction
    _write_patch_json(data_dir, "en-2023-09-01-1",
                      [{"type": "hero_update", "title": "Stadium Updates",
                        "heroes": [{"slug": "doomfist", "name_en": "Doomfist",
                                    "stadium_items": [{"lines_en": ["Mask"]}]}]}])
    result = PairResult(
        pairs=[{
            "id": "p-2023-07-01-1", "date": "2023-07-01",
            "en": {"patch_id": "en-2023-07-01-1", "date": "2023-07-01", "seq": 1,
                   "title": "Retail Patch Notes", "url": "u"},
            "cn": {"patch_id": "cn-2023-07-02-1", "date": "2023-07-02", "seq": 1,
                   "title": "《守望先锋》补丁说明", "url": "u"},
        }],
        unpaired_en=["en-2023-06-01-1", "en-2023-08-01-1", "en-2021-01-01-1", "en-2023-09-01-1"],
    )
    build_patches_index(data_dir, result)
    index = json.loads((data_dir / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert by_id["p-2023-07-01-1"]["categories"] == []            # earlier mention suppresses
    assert by_id["en-2023-06-01-1"]["categories"] == []           # roadmap mention only
    assert by_id["en-2023-08-01-1"]["categories"] == ["new_hero"] # clean intro
    assert by_id["en-2021-01-01-1"]["categories"] == []           # pre-OW2 era gate
    assert by_id["en-2023-09-01-1"]["categories"] == ["stadium"]  # stadium-only: no new_hero


def test_manual_categories_override(tmp_path):
    """data/manual_categories.json entries are unioned into categories;
    unknown keys are dropped; a missing file is tolerated."""
    from ow2_patch.pairing import PairResult, build_patches_index

    data_dir = tmp_path / "data"
    _write_patch_json(data_dir, "en-2026-01-02-1",
                      [{"type": "generic_update", "title": "General Updates", "heroes": []}])
    (data_dir / "manual_categories.json").write_text(
        json.dumps({"en-2026-01-02-1": ["season", "bogus"]}), encoding="utf-8")
    result = PairResult(pairs=[], unpaired_en=["en-2026-01-02-1"])
    build_patches_index(data_dir, result)
    index = json.loads((data_dir / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert by_id["en-2026-01-02-1"]["categories"] == ["season"]  # bogus dropped, no event scope hit


def test_malformed_manual_categories_tolerated(tmp_path):
    """A malformed manual_categories.json (hand-edit typo) must not break the
    rebuild."""
    from ow2_patch.pairing import PairResult, build_patches_index

    data_dir = tmp_path / "data"
    _write_patch_json(data_dir, "en-2026-01-02-1",
                      [{"type": "generic_update", "title": "General Updates", "heroes": []}])
    (data_dir / "manual_categories.json").write_text("{not json", encoding="utf-8")
    result = PairResult(pairs=[], unpaired_en=["en-2026-01-02-1"])
    build_patches_index(data_dir, result)
    index = json.loads((data_dir / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert by_id["en-2026-01-02-1"]["categories"] == []


def test_patches_index_hero_changes_field(tmp_path):
    """has_hero_changes = either side carries a balance hero block with actual
    change content: stadium-mask blocks, empty-change hero blocks (the
    en-2022-01-06-1 shape) and hero-less patches stay false; unpaired entries
    use their own content."""
    from ow2_patch.pairing import PairResult, build_patches_index

    data_dir = tmp_path / "data"
    # pair: EN side has no heroes, CN side has a balance hero block with a
    # general line → union true
    _write_patch_json(data_dir, "en-2026-03-01-1",
                      [{"type": "generic_update", "title": "Client Update", "heroes": []}])
    _write_patch_json(data_dir, "cn-2026-03-02-1",
                      [{"type": "hero_update", "title": "英雄更新",
                        "heroes": [{"slug": "ana", "name_en": "Ana",
                                    "general": ["弹夹容量从12提高到14。"]}]}])
    # stadium mask block with lines → false (cosmetic, not balance)
    _write_patch_json(data_dir, "cn-2026-03-03-1",
                      [{"type": "hero_update", "title": "英雄更新",
                        "heroes": [{"slug": "reinhardt-mask", "name_en": "Reinhardt Mask",
                                    "stadium_items": [{"lines_en": ["Mask skin"]}]}]}])
    # hero block with empty changes / no general / no perks → false
    _write_patch_json(data_dir, "en-2026-03-04-1",
                      [{"type": "hero_update", "title": "Hero Updates",
                        "heroes": [{"slug": "moira", "name_en": "Moira",
                                    "abilities": [{"name_en": "Fade", "changes": []}]}]}])
    # no hero blocks → false
    _write_patch_json(data_dir, "en-2026-03-05-1",
                      [{"type": "generic_update", "title": "Bug Fixes", "heroes": []}])
    # perk block → true
    _write_patch_json(data_dir, "en-2026-03-06-1",
                      [{"type": "hero_update", "title": "Hero Updates",
                        "heroes": [{"slug": "ana", "name_en": "Ana",
                                    "perks": [{"name_en": "Nano Boost"}]}]}])
    # named ability with non-empty changes → true
    _write_patch_json(data_dir, "en-2026-03-07-1",
                      [{"type": "hero_update", "title": "Hero Updates",
                        "heroes": [{"slug": "ana", "name_en": "Ana",
                                    "abilities": [{"name_en": "Biotic Rifle",
                                                   "changes": [{"text_en": "Damage increased from 70 to 75."}]}]}]}])
    result = PairResult(
        pairs=[{
            "id": "p-2026-03-01-1", "date": "2026-03-01",
            "en": {"patch_id": "en-2026-03-01-1", "date": "2026-03-01", "seq": 1,
                   "title": "Overwatch Patch Notes", "url": "u"},
            "cn": {"patch_id": "cn-2026-03-02-1", "date": "2026-03-02", "seq": 1,
                   "title": "《守望先锋》补丁说明", "url": "u"},
        }],
        unpaired_cn=["cn-2026-03-03-1"],
        unpaired_en=["en-2026-03-04-1", "en-2026-03-05-1", "en-2026-03-06-1", "en-2026-03-07-1"],
    )
    build_patches_index(data_dir, result)
    index = json.loads((data_dir / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert by_id["p-2026-03-01-1"]["has_hero_changes"] is True   # CN-side general line
    assert by_id["cn-2026-03-03-1"]["has_hero_changes"] is False  # stadium mask block
    assert by_id["en-2026-03-04-1"]["has_hero_changes"] is False  # empty change content
    assert by_id["en-2026-03-05-1"]["has_hero_changes"] is False  # no hero blocks
    assert by_id["en-2026-03-06-1"]["has_hero_changes"] is True   # perk block
    assert by_id["en-2026-03-07-1"]["has_hero_changes"] is True   # ability changes
    assert all(isinstance(p["has_hero_changes"], bool) for p in index["patches"])


def test_real_patches_index_hero_changes_invariants():
    """has_hero_changes marks patches that contribute to the standard balance
    history. The flag is mode-agnostic: special-mode patches carry it too, and
    the frontend gates the 「英雄改动」 badge on mode == standard."""
    index = json.loads((DATA / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert by_id["p-2026-08-11-1"]["has_hero_changes"] is True    # standard, 32 hero blocks
    assert by_id["p-2026-08-19-1"]["has_hero_changes"] is False   # standard, no hero blocks
    assert by_id["en-2022-10-04-1"]["has_hero_changes"] is False  # announcement, 0 hero blocks
    assert by_id["en-2022-01-06-1"]["has_hero_changes"] is False  # empty-change hero blocks
    assert by_id["p-2026-04-01-1"]["has_hero_changes"] is True    # april_fools: flag true, badge gated
    assert all(isinstance(p.get("has_hero_changes"), bool) for p in index["patches"])
    # the frontend mode gate is necessary: at least one special-mode patch
    # carries the flag without ever showing the badge
    assert any(p["mode"] != "standard" and p["has_hero_changes"] for p in index["patches"])


def test_patches_index_first_section_fields(tmp_path):
    """first_section_en/cn mirror each side's first NON-EMPTY section title;
    patches with no titled sections (OW1 raw_text) yield ""."""
    from ow2_patch.pairing import PairResult, build_patches_index

    data_dir = tmp_path / "data"
    _write_patch_json(data_dir, "en-2026-08-11-1", [
        {"type": "generic_update", "title": "Reign of Talon - Season 4", "heroes": []},
        {"type": "hero_update", "title": "Tank", "heroes": [{"slug": "orisa"}]},
    ])
    _write_patch_json(data_dir, "cn-2026-08-12-1", [
        {"type": "generic_update", "title": "", "heroes": []},
        {"type": "hero_update", "title": "重装", "heroes": [{"slug": "orisa"}]},
    ])
    _write_patch_json(data_dir, "en-2016-05-27-1", [])  # raw_text-only page
    result = PairResult(
        pairs=[{
            "id": "p-2026-08-11-1", "date": "2026-08-11",
            "en": {"patch_id": "en-2026-08-11-1", "date": "2026-08-11", "seq": 1,
                   "title": "Overwatch Patch Notes", "url": "u"},
            "cn": {"patch_id": "cn-2026-08-12-1", "date": "2026-08-12", "seq": 1,
                   "title": "《守望先锋》补丁说明", "url": "u"},
        }],
        unpaired_en=["en-2016-05-27-1"],
    )
    build_patches_index(data_dir, result)
    index = json.loads((data_dir / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    pair = by_id["p-2026-08-11-1"]
    assert pair["first_section_en"] == "Reign of Talon - Season 4"
    # an empty leading title is skipped: first non-empty section wins
    assert pair["first_section_cn"] == "重装"
    legacy = by_id["en-2016-05-27-1"]
    assert legacy["first_section_en"] == ""
    assert legacy["first_section_cn"] is None


def test_real_patches_index_first_section_invariants():
    """Regenerated index: every entry carries both first_section keys, and a
    known season patch exposes its first section title on both sides."""
    index = json.loads((DATA / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    for p in index["patches"]:
        assert "first_section_en" in p and "first_section_cn" in p
    assert by_id["p-2026-08-11-1"]["first_section_en"].startswith("Reign of Talon")
    assert by_id["p-2026-08-11-1"]["first_section_cn"]


def test_patches_index_chars_fields(tmp_path):
    """chars_en/cn sum every string inside sections plus raw_text; raw_text-only
    patches count the raw blob; the missing side of an unpaired entry is None."""
    from ow2_patch.pairing import PairResult, build_patches_index

    data_dir = tmp_path / "data"
    _write_patch_json(data_dir, "en-2026-08-11-1", [
        {"type": "generic_update", "title": "Reign of Talon - Season 4", "heroes": []},
        {"type": "hero_update", "title": "Tank",
         "heroes": [{"slug": "orisa", "name_cn": "奥丽莎", "name_en": "Orisa",
                     "general": [{"text_cn": "生命值提高至 250。",
                                  "text_en": "HP increased to 250."}]}]},
    ])
    _write_patch_json(data_dir, "cn-2026-08-12-1", [
        {"type": "generic_update", "title": "黑爪之治——第4赛季", "heroes": []},
    ])
    parts = "en-2016-05-27-1".split("-")
    (data_dir / "patches" / "en").mkdir(parents=True, exist_ok=True)
    (data_dir / "patches" / "en" / "2016-05-27-1.json").write_text(
        json.dumps({"id": "en-2016-05-27-1", "site": "en", "date": "2016-05-27",
                    "title": "t", "url": "u", "sections": [], "raw_text": "abc 原始文本"},
                   ensure_ascii=False), encoding="utf-8")
    result = PairResult(
        pairs=[{
            "id": "p-2026-08-11-1", "date": "2026-08-11",
            "en": {"patch_id": "en-2026-08-11-1", "date": "2026-08-11", "seq": 1,
                   "title": "Overwatch Patch Notes", "url": "u"},
            "cn": {"patch_id": "cn-2026-08-12-1", "date": "2026-08-12", "seq": 1,
                   "title": "《守望先锋》补丁说明", "url": "u"},
        }],
        unpaired_en=["en-2016-05-27-1"],
    )
    build_patches_index(data_dir, result)
    index = json.loads((data_dir / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    pair = by_id["p-2026-08-11-1"]
    # section titles + type markers + hero slug/names + general text (both
    # languages); every string value inside sections counts, keys do not
    assert pair["chars_en"] == 98
    assert pair["chars_cn"] == 24
    legacy = by_id["en-2016-05-27-1"]
    assert legacy["chars_en"] == len("abc 原始文本")
    assert legacy["chars_cn"] is None


def test_real_patches_index_chars_invariants():
    """Regenerated index: every entry carries both chars keys; a season patch
    is an order of magnitude larger than a hotfix."""
    index = json.loads((DATA / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    for p in index["patches"]:
        assert "chars_en" in p and "chars_cn" in p
    assert by_id["p-2026-08-11-1"]["chars_en"] > 10000
    assert by_id["p-2026-08-11-1"]["chars_cn"] > 0
    assert by_id["en-2026-08-20-1"]["chars_en"] > 0


# ---------- structural-signature weighting ----------

def _write_patch_json(data_dir, patch_id, sections):
    parts = patch_id.split("-")
    site = parts[0]
    d = data_dir / "patches" / site
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{'-'.join(parts[1:4])}-{parts[4]}.json").write_text(
        json.dumps({"id": patch_id, "site": site, "date": "-".join(parts[1:4]),
                    "title": f"{site} {patch_id}", "url": f"https://x/{patch_id}",
                    "sections": sections},
                   ensure_ascii=False), encoding="utf-8")


def test_signature_beats_same_day_mispair(tmp_path):
    """The 2026-08-19/20 regression: a CN patch whose true partner is the
    1-day-lag EN page must beat a same-day EN page with different content."""
    data_dir = tmp_path / "data"
    # EN 8.19 = Client Update (no heroes); EN 8.20 = hotfix (Mizuki);
    # CN 8.20 = translation of EN 8.19 (no heroes)
    _write_patch_json(data_dir, "en-2026-08-19-1",
                      [{"type": "generic_update", "title": "Client Update", "heroes": []},
                       {"type": "generic_update", "title": "Bug Fixes", "heroes": []}])
    _write_patch_json(data_dir, "en-2026-08-20-1",
                      [{"type": "generic_update", "title": "Hotfix Update", "heroes": []},
                       {"type": "hero_update", "title": "Bug Fixes",
                        "heroes": [{"slug": "mizuki"}]}])
    _write_patch_json(data_dir, "cn-2026-08-20-1",
                      [{"type": "generic_update", "title": "游戏客户端更新", "heroes": []},
                       {"type": "generic_update", "title": "错误修复", "heroes": []}])
    en = [make_patch("en", "2026-08-19", title="Overwatch Patch Notes – August 19, 2026"),
          make_patch("en", "2026-08-20", title="Overwatch Patch Notes – August 20, 2026")]
    cn = [make_patch("cn", "2026-08-20", title="《守望先锋》补丁说明——2026年8月20日")]
    old = pair_patches(en, cn)  # no signatures: same-day mispair
    assert old.pairs[0]["en"]["patch_id"] == "en-2026-08-20-1"
    new = pair_patches(en, cn, data_dir=data_dir)
    assert new.pairs[0]["en"]["patch_id"] == "en-2026-08-19-1"
    assert new.pairs[0]["cn"]["patch_id"] == "cn-2026-08-20-1"
    assert new.unpaired_en == ["en-2026-08-20-1"]


def test_signature_mismatch_keeps_max_cardinality(tmp_path):
    """A signature-mismatched edge is penalized, never dropped: when it is the
    only candidate the pair still forms (maximum cardinality preserved)."""
    data_dir = tmp_path / "data"
    _write_patch_json(data_dir, "en-2026-08-19-1",
                      [{"type": "hero_update", "title": "Tank",
                        "heroes": [{"slug": "orisa"}]}])
    _write_patch_json(data_dir, "cn-2026-08-20-1",
                      [{"type": "hero_update", "title": "重装",
                        "heroes": [{"slug": "reinhardt"}]}])
    en = [make_patch("en", "2026-08-19", title="Overwatch Patch Notes – August 19, 2026")]
    cn = [make_patch("cn", "2026-08-20", title="《守望先锋》补丁说明——2026年8月20日")]
    result = pair_patches(en, cn, data_dir=data_dir)
    assert len(result.pairs) == 1  # still paired, nothing better exists


def test_signature_strips_trailing_empty_generic_sections():
    """Trivial section-count differences (an empty trailing generic_update
    stub on one side only) must not break the signature match."""
    from ow2_patch.pairing import _patch_signature

    sig = _patch_signature({
        "sections": [
            {"type": "generic_update", "title": "回放代码重置", "heroes": []},
            {"type": "hero_update", "title": "重装",
             "heroes": [{"slug": "d-va"}]},
            {"type": "generic_update", "title": "Map Updates", "heroes": []},
        ],
    })
    sig_extra = _patch_signature({
        "sections": [
            {"type": "generic_update", "title": "Replay Codes Reset", "heroes": []},
            {"type": "hero_update", "title": "Tank", "heroes": [{"slug": "d-va"}]},
            {"type": "generic_update", "title": "Map Updates", "heroes": []},
            {"type": "generic_update", "title": "", "heroes": []},
        ],
    })
    assert sig == sig_extra


def test_real_data_pairing_signature_invariants():
    """Real data with signatures: the known mispairs are repaired, pair count
    unchanged, and every pair's EN/CN signatures match where expected."""
    en, cn = patch_meta_from_manifest(DATA)
    old = pair_patches(en, cn)
    new = pair_patches(en, cn, data_dir=DATA)
    assert len(new.pairs) == len(old.pairs) == 56  # max cardinality preserved (+ cn-2026-02-11-1)
    by_en = {p["en"]["patch_id"]: p["cn"]["patch_id"] for p in new.pairs}
    # 2026-08-19/20 regression fixed
    assert by_en["en-2026-08-19-1"] == "cn-2026-08-20-1"
    assert "en-2026-08-20-1" not in by_en and "en-2026-08-20-1" in new.unpaired_en
    # 2025 mispairs fixed (true partners restored)
    assert by_en["en-2025-04-22-1"] == "cn-2025-04-23-1"
    assert by_en["en-2025-05-14-1"] == "cn-2025-05-16-1"
    assert by_en["en-2025-05-22-1"] == "cn-2025-05-23-1"
    # 2025-07-09: same-day Juno hotfix must not absorb the 7-hero CN page
    assert by_en["en-2025-07-03-1"] == "cn-2025-07-09-1"
    assert "en-2025-07-09-1" not in by_en and "en-2025-07-09-1" in new.unpaired_en
    # Feb-2025: the all-generic-empty 2-section hotfix must NOT steal the
    # Season-15 CN page from its true partner (normalization to empty would)
    assert by_en["en-2025-02-18-1"] == "cn-2025-02-19-1"
    assert "en-2025-02-20-1" not in by_en and "en-2025-02-20-1" in new.unpaired_en
