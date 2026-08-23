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
    assert len(en) == 343 and len(cn) == 55  # 342 EN + en-2026-08-20-1
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


def test_real_patches_index_qp_hacked_content_flag():
    """Content mentions of Quick Play: Hacked carry a display-only flag: the
    badge shows without reclassifying the patch, so standard-titled mixed
    patches (p-2026-01-08-1) keep their hero data in the standard history."""
    index = json.loads((DATA / "patches_index.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in index["patches"]}
    assert by_id["p-2026-01-08-1"]["content_qp_hacked"] is True  # QP Hacked Assault block
    assert by_id["p-2026-07-30-1"]["content_qp_hacked"] is True  # limited-time 6v6 dev note
    assert by_id["p-2026-01-08-1"]["mode"] == "standard"  # badge only, no reclassification
    assert by_id["p-2026-08-11-1"]["content_qp_hacked"] is False
    assert all("content_qp_hacked" in p for p in index["patches"])


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
    assert len(new.pairs) == len(old.pairs) == 55  # max cardinality preserved
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
