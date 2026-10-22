"""Entry search index + official post-edit records tests."""

from __future__ import annotations

import json
import pathlib

from ow2_patch.entries import (
    build_entries_index,
    build_official_edits,
    entry_key,
    merged_change_count,
    write_entries_index,
    write_official_edits,
)
from ow2_patch.schema import INDEX_SCHEMA_VERSION

REAL_DATA = pathlib.Path(__file__).resolve().parent.parent / "data"

DIM_PREFIX = {"weapon": "weapon", "ability": "ability", "perk": "perk",
              "hero_attr": "attr", "hero": "hero"}


def make_entry(**kw):
    base = {"kind": "ability", "dimension": "ability",
            "ability_slug": "biotic-field", "ability_en": "Biotic Field",
            "ability_cn": "生物力场", "patch": "en-2026-06-30-1", "date": "2026-06-30"}
    base.update(kw)
    return base


# ---------- entry_key parity with web/app.js ----------

def test_entry_key_ability_and_weapon():
    assert entry_key(make_entry()) == "ability::biotic-field"
    assert entry_key(make_entry(dimension="weapon")) == "weapon::biotic-field"


def test_entry_key_falls_back_to_names():
    assert entry_key(make_entry(ability_slug=None)) == "ability::Biotic Field"
    assert entry_key(make_entry(ability_slug=None, ability_en=None)) == "ability::生物力场"


def test_entry_key_perk():
    e = {"kind": "perk", "dimension": "perk", "perk_slug": "chronal-dash",
         "perk_cn": "时空疾冲", "perk_en": None}
    assert entry_key(e) == "perk::chronal-dash"
    e2 = {"kind": "perk", "dimension": "perk", "perk_cn": "时空疾冲"}
    assert entry_key(e2) == "perk::时空疾冲"


def test_entry_key_hero_attr_fallback_other():
    assert entry_key({"dimension": "hero_attr", "subject": "health"}) == "attr::health"
    assert entry_key({"dimension": "hero_attr", "metric": "move_speed"}) == "attr::move_speed"
    assert entry_key({"dimension": "hero_attr"}) == "attr::other"


def test_entry_key_excludes_other_dimension():
    assert entry_key({"dimension": "other"}) is None
    assert entry_key({"kind": "general"}) is None


# ---------- merged change count (port of web/app.js mergeEntryRecords) ----------

PAIR_MAP = {"en-2026-06-30-1": "p-2026-06-30-1", "cn-2026-07-01-1": "p-2026-06-30-1"}


def _pair(en_text="Damage increased from 50 to 60.", cn_text="伤害从50提高至60。"):
    return [
        make_entry(patch="en-2026-06-30-1", date="2026-06-30", site="en", text_en=en_text),
        make_entry(patch="cn-2026-07-01-1", date="2026-07-01", site="cn", text_cn=cn_text),
    ]


def test_merged_change_count_merges_shared_numbers():
    assert merged_change_count(_pair(), PAIR_MAP) == 1


def test_merged_change_count_vetoes_disjoint_numbers():
    """The numeric fingerprint veto keeps an EN/CN pair apart when neither
    side's numbers appear on the other (they are different changes)."""
    records = _pair(
        en_text="Max overhealth reduced to 30% (Down from 65%).",
        cn_text="过量生命值从100降低至75。",
    )
    assert merged_change_count(records, PAIR_MAP) == 2


def test_merged_change_count_without_pairing_data_is_identity():
    assert merged_change_count(_pair(), {}) == 2
    # unequal side counts never merge either
    records = _pair() + [make_entry(patch="en-2026-06-30-1", date="2026-06-30", site="en")]
    assert merged_change_count(records, PAIR_MAP) == 3


def test_entries_index_changes_field(tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "heroes").mkdir(parents=True)
    (data_dir / "heroes" / "ana.json").write_text(json.dumps({
        "slug": "ana", "names": {"en": "Ana", "cn": "安娜"}, "role": "support",
        "timeline": _pair(), "values": {}}, ensure_ascii=False), encoding="utf-8")
    (data_dir / "patches_index.json").write_text(json.dumps({
        "schema_version": 1, "updated": "", "patches": [
            {"id": "p-2026-06-30-1", "date": "2026-06-30",
             "patch_id_en": "en-2026-06-30-1", "patch_id_cn": "cn-2026-07-01-1"}]},
        ensure_ascii=False), encoding="utf-8")
    idx = build_entries_index(data_dir)
    ability = next(e for e in idx["entries"] if e["dimension"] == "ability")
    assert ability["count"] == 2      # two raw records
    assert ability["changes"] == 1    # one merged row on the detail page
    hero = next(e for e in idx["entries"] if e["dimension"] == "hero")
    assert hero["changes"] == 1


# ---------- build_official_edits ----------

def test_official_edits_groups_modified_only(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "changelog.jsonl").write_text(
        '{"ts": "2026-08-16T04:09:09Z", "kind": "new", "patch_id": "en-2016-05-27-1"}\n'
        '{"ts": "2026-08-16T04:09:09Z", "kind": "modified", "patch_id": "en-2016-05-27-1", '
        '"date": "2016-05-27", "title": "T", "url": "u1"}\n'
        '{"ts": "2026-08-17T04:13:37Z", "kind": "modified", "patch_id": "en-2016-05-27-1", '
        '"date": "2016-05-27", "title": "T", "url": "u2"}\n'
        '{"ts": "2026-08-17T04:13:37Z", "kind": "modified", "patch_id": "cn-2026-06-17-1", '
        '"date": "2026-06-17", "title": "C", "url": "u3", "cosmetic": true}\n',
        encoding="utf-8")
    edits = build_official_edits(data_dir)
    assert edits["updated"] == "2026-08-17T04:13:37Z"
    assert set(edits["edits"]) == {"en-2016-05-27-1", "cn-2026-06-17-1"}
    assert [e["ts"] for e in edits["edits"]["en-2016-05-27-1"]] == [
        "2026-08-16T04:09:09Z", "2026-08-17T04:13:37Z"]
    assert edits["edits"]["cn-2026-06-17-1"][0].get("cosmetic") is True
    assert "cosmetic" not in edits["edits"]["en-2016-05-27-1"][0]


def test_official_edits_missing_changelog(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    result = build_official_edits(data_dir)
    assert result["updated"] == ""
    assert result["edits"] == {}
    assert result["schema_version"] == INDEX_SCHEMA_VERSION


# ---------- build_entries_index (synthetic) ----------

def _write_synthetic(data_dir):
    data_dir.mkdir(parents=True)
    (data_dir / "heroes_index.json").write_text(json.dumps(
        {"updated": "2026-07-01T00:00:00Z",
         "heroes": [{"slug": "ana", "en": "Ana", "cn": "安娜", "role": "support"}]},
        ensure_ascii=False), encoding="utf-8")
    heroes = data_dir / "heroes"
    heroes.mkdir()
    (heroes / "ana.json").write_text(json.dumps({
        "slug": "ana", "names": {"en": "Ana", "cn": "安娜"}, "role": "support",
        "timeline": [
            make_entry(patch="en-2016-05-27-1", date="2016-05-27"),
            make_entry(patch="en-2026-06-30-1", date="2026-06-30"),
            {"kind": "general", "dimension": "hero_attr", "subject": "health",
             "patch": "cn-2026-07-01-1", "date": "2026-07-01"},
            {"kind": "general", "dimension": "other", "patch": "cn-2026-07-01-1",
             "date": "2026-07-01", "text_cn": "不纳入词条"},
        ],
        "values": {}}, ensure_ascii=False), encoding="utf-8")
    (data_dir / "ability_map.json").write_text(json.dumps(
        {"abilities": {"biotic-field": {"heroes": ["ana"], "name_en": "Biotic Field",
                                        "name_cn": "生物力场",
                                        "cn_variants": ["生物力场", "禁疗手雷"],
                                        "en_variants": ["Biotic Field"]}},
         "perks": {}}, ensure_ascii=False), encoding="utf-8")
    (data_dir / "changelog.jsonl").write_text(
        '{"ts": "2026-08-16T04:09:09Z", "kind": "modified", "patch_id": "en-2016-05-27-1", '
        '"date": "2016-05-27", "title": "T", "url": "u"}\n', encoding="utf-8")


def test_entries_index_synthetic(tmp_path):
    data_dir = tmp_path / "data"
    _write_synthetic(data_dir)
    edits = build_official_edits(data_dir)
    idx = build_entries_index(data_dir, edits)
    assert idx["updated"] == "2026-07-01T00:00:00Z"
    keys = {e["key"] for e in idx["entries"]}
    assert keys == {"hero::ana", "ana::ability::biotic-field", "ana::attr::health"}
    ability = next(e for e in idx["entries"] if e["key"] == "ana::ability::biotic-field")
    assert ability["name_cn"] == "生物力场" and ability["name_en"] == "Biotic Field"
    assert ability["variants"] == ["生物力场", "禁疗手雷", "Biotic Field"]
    assert ability["count"] == 2
    assert ability["changes"] == 2  # no patches_index in this fixture: nothing merges
    assert ability["first_date"] == "2016-05-27" and ability["last_date"] == "2026-06-30"
    assert ability["edited"] is True
    health = next(e for e in idx["entries"] if e["key"] == "ana::attr::health")
    assert health["name_cn"] == "生命值" and health["name_en"] == "health"
    hero = next(e for e in idx["entries"] if e["key"] == "hero::ana")
    assert hero["count"] == 4 and hero["edited"] is True


def test_entries_index_standard_only_modes(tmp_path):
    """Special-mode records (mode != standard) must not count toward entries."""
    data_dir = tmp_path / "data"
    (data_dir / "heroes").mkdir(parents=True)
    (data_dir / "heroes" / "ana.json").write_text(json.dumps({
        "slug": "ana", "names": {"en": "Ana", "cn": "安娜"}, "role": "support",
        "timeline": [
            {**make_entry(patch="en-2025-03-25-1", date="2025-03-25"), "mode": "standard"},
            {**make_entry(patch="en-2025-04-01-1", date="2025-04-01"), "mode": "april_fools"},
            {**make_entry(patch="en-2025-04-01-1", date="2025-04-01"), "mode": "april_fools"},
        ],
        "values": {}}, ensure_ascii=False), encoding="utf-8")
    idx = build_entries_index(data_dir)
    ability = next(e for e in idx["entries"] if e["dimension"] == "ability")
    assert ability["count"] == 1  # the two April Fools records are excluded
    assert ability["first_date"] == ability["last_date"] == "2025-03-25"
    hero = next(e for e in idx["entries"] if e["dimension"] == "hero")
    assert hero["count"] == 1
    # records without a mode default to standard (backwards compatible)
    assert build_entries_index(data_dir)["entries"]  # still builds


def test_entries_index_missing_aux_files(tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "heroes").mkdir(parents=True)
    (data_dir / "heroes" / "ana.json").write_text(json.dumps({
        "slug": "ana", "names": {"en": "Ana", "cn": "安娜"}, "role": "support",
        "timeline": [make_entry(date="2026-06-30")], "values": {}},
        ensure_ascii=False), encoding="utf-8")
    idx = build_entries_index(data_dir)
    ability = next(e for e in idx["entries"] if e["dimension"] == "ability")
    # falls back to record names when ability_map is absent
    assert ability["name_en"] == "Biotic Field" and ability["name_cn"] == "生物力场"
    hero = next(e for e in idx["entries"] if e["dimension"] == "hero")
    assert hero["hero_cn"] == "安娜"


# ---------- real data invariants ----------

def test_real_entries_index_invariants():
    edits = build_official_edits(REAL_DATA)
    idx = build_entries_index(REAL_DATA, edits)
    entries = idx["entries"]
    assert entries, "real entries index must not be empty"
    keys = [e["key"] for e in entries]
    assert len(keys) == len(set(keys)), "entry keys must be unique"

    prefix_by_dim = {"weapon": "weapon", "ability": "ability", "perk": "perk",
                     "hero_attr": "attr", "hero": "hero"}
    for e in entries:
        parts = e["key"].split("::")
        if e["dimension"] == "hero":
            assert parts == ["hero", e["hero_slug"]], e["key"]
        else:
            assert len(parts) == 3, e["key"]
            assert parts[0] == e["hero_slug"], e["key"]
            assert parts[1] == prefix_by_dim[e["dimension"]], e["key"]
        assert e["count"] > 0
        assert e["first_date"] <= e["last_date"]
        assert e["name_cn"] or e["name_en"], e["key"]
    # multi-hero ability appears once per hero (the generic "General" ability
    # section spans several heroes; quick-melee no longer qualifies since the
    # April Fools 2026 re-tag left only doomfist's standard records)
    qm = [e for e in entries if e["slug"] == "general"]
    assert len(qm) >= 2
    assert len({e["hero_slug"] for e in qm}) == len(qm)


def js_entry_key(rec):
    """Independent reimplementation of web/app.js entryKey(), for parity checks.

    Deliberately NOT calling entry_key(), so a future drift between the two
    implementations is caught instead of asserted into existence.
    """
    dim = rec.get("dimension") or ("perk" if rec.get("kind") == "perk" else "other")
    if dim in ("weapon", "ability"):
        return f"{dim}::{rec.get('ability_slug') or rec.get('ability_en') or rec.get('ability_cn') or ''}"
    if dim == "perk":
        return f"perk::{rec.get('perk_slug') or rec.get('perk_cn') or rec.get('perk_en') or ''}"
    if dim == "hero_attr":
        return f"attr::{rec.get('subject') or rec.get('metric') or 'other'}"
    return "other::"


def test_real_entry_key_matches_js_semantics():
    """Python entry_key must agree with app.js semantics on every real record.

    app.js groups slug-less weapon/ability records under a bare 'dim::' key and
    all other-dimension records under 'other::'; the index intentionally drops
    those (they are not searchable entries), so the two only differ there.
    """
    for hero_file in sorted((REAL_DATA / "heroes").glob("*.json")):
        hero = json.loads(hero_file.read_text(encoding="utf-8"))
        for rec in hero["timeline"]:
            js_key = js_entry_key(rec)
            py_key = entry_key(rec)
            if js_key.endswith("::"):
                assert py_key is None, (hero["slug"], rec)
            else:
                assert py_key == js_key, (hero["slug"], rec)


def test_real_entries_parity_with_hero_timelines():
    """Every searchable STANDARD timeline record maps to an existing index key
    (special-mode records are intentionally excluded from the standard index)."""
    edits = build_official_edits(REAL_DATA)
    idx = build_entries_index(REAL_DATA, edits)
    keys = {e["key"] for e in idx["entries"]}
    for hero_file in sorted((REAL_DATA / "heroes").glob("*.json")):
        hero = json.loads(hero_file.read_text(encoding="utf-8"))
        for rec in hero["timeline"]:
            if (rec.get("mode") or "standard") != "standard":
                continue  # April Fools / experiments / trials are not searchable
            key = entry_key(rec)
            if key is None:
                continue
            assert f"{hero['slug']}::{key}" in keys, (hero["slug"], key)


def test_real_entries_changes_field():
    """`changes` must be a plausible merged-row count on real data, and must be
    strictly lower than `count` where the archive has EN/CN pairs."""
    idx = build_entries_index(REAL_DATA, build_official_edits(REAL_DATA))
    by_key = {e["key"]: e for e in idx["entries"]}
    for entry in idx["entries"]:
        assert 1 <= entry["changes"] <= entry["count"], entry["key"]
    # the whole 2026-10-06 hotfix landed in one logical patch, but as 12 rows
    assert by_key["sombra::ability::hotfix"]["count"] == 24
    assert by_key["sombra::ability::hotfix"]["changes"] == 12
    # 18 raw records, one EN/CN pair merged -> 17 rows on the detail page
    assert by_key["soldier-76::weapon::heavy-pulse-rifle"]["count"] == 18
    assert by_key["soldier-76::weapon::heavy-pulse-rifle"]["changes"] == 17


def test_real_edited_flag():
    """Recorded official edits: the cn-2025-07-25-1 recovery backfill and the
    2026-09-08/09 pair that was re-scraped with fuller content. Entries touched
    by those patches carry edited=True; untouched ones stay False."""
    edits = build_official_edits(REAL_DATA)
    idx = build_entries_index(REAL_DATA, edits)
    assert {"cn-2025-07-25-1", "en-2026-09-08-1", "cn-2026-09-09-1"} <= set(edits["edits"])
    by_key = {e["key"]: e for e in idx["entries"]}
    assert "ana::weapon::biotic-rifle" in by_key  # ana has legacy 2016 records
    assert by_key["ana::weapon::biotic-rifle"]["edited"] is False
    edited_keys = {e["key"] for e in idx["entries"] if e["edited"]}
    # at least the heroes whose timelines gained the recovered 2025-07-25 content
    assert {"hero::d-va", "hero::freja", "hero::juno", "hero::mei"} <= edited_keys


# ---------- write + idempotency ----------

def test_write_and_roundtrip(tmp_path):
    data_dir = tmp_path / "data"
    _write_synthetic(data_dir)
    edits = build_official_edits(data_dir)
    write_official_edits(data_dir, edits)
    write_entries_index(data_dir, build_entries_index(data_dir, edits))
    assert json.loads((data_dir / "official_edits.json").read_text(encoding="utf-8")) == edits
    assert json.loads((data_dir / "entries_index.json").read_text(encoding="utf-8"))["entries"]


def test_build_functions_idempotent():
    edits_a = build_official_edits(REAL_DATA)
    edits_b = build_official_edits(REAL_DATA)
    assert edits_a == edits_b
    idx_a = build_entries_index(REAL_DATA, edits_a)
    idx_b = build_entries_index(REAL_DATA, edits_b)
    assert idx_a == idx_b
