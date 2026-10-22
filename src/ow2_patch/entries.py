"""Entry-level search index and official post-edit records for the web site.

build_entries_index aggregates the per-hero timelines into one flat, searchable
list of entries (ability / weapon / perk / hero attribute / hero), reusing the
exact grouping-key scheme the web frontend uses (web/app.js entryKey). It is a
pure function of the already-deterministic hero files, so regeneration is
idempotent. build_official_edits surfaces the kind=modified changelog events
(patch-level) as a compact patch_id -> edits map for frontend annotation.
"""

from __future__ import annotations

import json
import pathlib
import re

from .schema import INDEX_SCHEMA_VERSION

DIM_ORDER = ["weapon", "ability", "perk", "hero_attr", "hero"]

# Mirrors web/app.js ATTR_LABEL (hero-attribute display names).
ATTR_CN = {
    "health": "生命值",
    "ultimate_cost": "终极技能消耗",
    "move_speed": "移动速度",
    "base_stat": "基础属性",
    "other": "其他",
}

_DIGITS_RE = re.compile(r"\d+(?:\.\d+)?")


def entry_key(entry: dict) -> str | None:
    """Grouping key, byte-for-byte compatible with web/app.js entryKey()."""
    dim = entry.get("dimension")
    if dim in ("weapon", "ability"):
        slug = entry.get("ability_slug") or entry.get("ability_en") or entry.get("ability_cn")
        return f"{dim}::{slug}" if slug else None
    if dim == "perk":
        slug = entry.get("perk_slug") or entry.get("perk_cn") or entry.get("perk_en")
        return f"perk::{slug}" if slug else None
    if dim == "hero_attr":
        return f"attr::{entry.get('subject') or entry.get('metric') or 'other'}"
    return None


def _js_entry_key(record: dict) -> str:
    """Exact mirror of web/app.js entryKey(): never null.

    Records outside the indexed dimensions group under ``other::`` — that matters
    because the merge (unlike the index) still counts and pairs those records, so
    a hero-wide merged count must use this key rather than ``entry_key()``.
    """
    dim = record.get("dimension") or ("perk" if record.get("kind") == "perk" else "other")
    if dim in ("weapon", "ability"):
        slug = record.get("ability_slug") or record.get("ability_en") or record.get("ability_cn") or ""
        return f"{dim}::{slug}"
    if dim == "perk":
        slug = record.get("perk_slug") or record.get("perk_cn") or record.get("perk_en") or ""
        return f"perk::{slug}"
    if dim == "hero_attr":
        return f"attr::{record.get('subject') or record.get('metric') or 'other'}"
    return "other::"


def _load_pair_map(data_dir: pathlib.Path) -> dict[str, str]:
    """patch_id -> logical patch id, mirroring web/app.js buildPairMap().

    Reads the already-written patches_index (regenerate_all builds it before the
    entries index). A missing file means "no pairing data": every patch maps to
    itself, so nothing merges — which is exactly what the synthetic fixtures in
    tests/test_entries.py expect.
    """
    path = data_dir / "patches_index.json"
    if not path.exists():
        return {}
    try:
        patches = json.loads(path.read_text(encoding="utf-8")).get("patches", [])
    except (OSError, json.JSONDecodeError):
        return {}
    pair_map: dict[str, str] = {}
    for patch in patches:
        logical_id = patch.get("id")
        if not logical_id:
            continue
        for side in ("patch_id_en", "patch_id_cn"):
            if patch.get(side):
                pair_map[patch[side]] = logical_id
    return pair_map


def _numbers_overlap(a: str, b: str) -> bool:
    """Same veto as web/app.js numbersOverlap(): two sides that both carry
    numbers must share at least one exact numeric token."""
    ta = _DIGITS_RE.findall(a or "")
    tb = set(_DIGITS_RE.findall(b or ""))
    if not ta or not tb:
        return True
    return any(token in tb for token in ta)


def merged_change_count(records: list[dict], pair_map: dict[str, str]) -> int:
    """Number of rows web/app.js will render for these records.

    Line-by-line port of mergeEntryRecords(): group paired EN/CN records of the
    same change, merge when both sides have equal counts AND the key is an
    ability/weapon/perk (or the pair is one-to-one) AND the numeric fingerprints
    agree; leave everything else as its own row. The frontend uses this number
    for the entry card, so tools/_smoke_web.js asserts the two implementations
    agree on every real entry.
    """
    groups: dict[tuple[str, str], dict[str, list[int]]] = {}
    for index, record in enumerate(records):
        logical_id = pair_map.get(record.get("patch") or "")
        if not logical_id:
            continue
        bucket = groups.setdefault((logical_id, _js_entry_key(record)), {"en": [], "cn": []})
        bucket["en" if record.get("site") == "en" else "cn"].append(index)

    consumed: set[int] = set()
    rows = 0
    for index, record in enumerate(records):
        if index in consumed:
            continue
        logical_id = pair_map.get(record.get("patch") or "")
        if logical_id:
            key = _js_entry_key(record)
            bucket = groups[(logical_id, key)]
            en, cn = bucket["en"], bucket["cn"]
            one_to_one = len(en) == 1 and len(cn) == 1
            mergeable = key.split("::", 1)[0] in ("ability", "weapon", "perk")
            if len(en) == len(cn) and (mergeable or one_to_one):
                position = en.index(index) if record.get("site") == "en" else cn.index(index)
                en_index, cn_index = en[position], cn[position]
                if _numbers_overlap(records[en_index].get("text_en") or "",
                                    records[cn_index].get("text_cn") or ""):
                    rows += 1
                    consumed.add(en_index)
                    consumed.add(cn_index)
                    continue
        rows += 1
    return rows


def build_official_edits(data_dir: pathlib.Path) -> dict:
    """Group changelog.jsonl kind=modified events by patch_id, ts ascending."""
    path = data_dir / "changelog.jsonl"
    edits: dict[str, list[dict]] = {}
    updated = ""
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("kind") != "modified":
                continue
            entry = {
                "ts": rec.get("ts"),
                "date": rec.get("date"),
                "title": rec.get("title"),
                "url": rec.get("url"),
            }
            if rec.get("cosmetic"):
                entry["cosmetic"] = True
            edits.setdefault(rec.get("patch_id"), []).append(entry)
            if rec.get("ts", "") > updated:
                updated = rec["ts"]
    for events in edits.values():
        events.sort(key=lambda e: e["ts"])
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "updated": updated,
        "edits": edits,
    }


def write_official_edits(data_dir: pathlib.Path, edits: dict) -> None:
    with open(data_dir / "official_edits.json", "w", encoding="utf-8") as fh:
        json.dump(edits, fh, ensure_ascii=False, indent=1)


def build_entries_index(data_dir: pathlib.Path, official_edits: dict | None = None) -> dict:
    """Flat search index of every searchable entry across all heroes.

    Each entry carries `count` (raw standard records, both sites counted) and
    `changes` (rows the web detail page will actually render, i.e. EN/CN pairs
    merged). The frontend shows `changes` so the card can never disagree with
    the page it opens.
    """
    edits = (official_edits or {}).get("edits", {})
    pair_map = _load_pair_map(data_dir)

    heroes_meta: dict[str, dict] = {}
    updated = ""
    heroes_index_path = data_dir / "heroes_index.json"
    if heroes_index_path.exists():
        heroes_index = json.loads(heroes_index_path.read_text(encoding="utf-8"))
        for h in heroes_index.get("heroes", []):
            heroes_meta[h["slug"]] = h
        updated = heroes_index.get("updated", "")

    ability_map_path = data_dir / "ability_map.json"
    names: dict[str, dict] = {}
    variants: dict[str, list[str]] = {}
    if ability_map_path.exists():
        ability_map = json.loads(ability_map_path.read_text(encoding="utf-8"))
        for bucket in ("abilities", "perks"):
            for slug, rec in ability_map.get(bucket, {}).items():
                names[slug] = rec
                vars_ = [v for v in (rec.get("cn_variants") or []) + (rec.get("en_variants") or []) if v]
                variants[slug] = vars_

    entries: list[dict] = []
    for hero_file in sorted((data_dir / "heroes").glob("*.json")):
        hero = json.loads(hero_file.read_text(encoding="utf-8"))
        slug = hero["slug"]
        meta = heroes_meta.get(slug, {})
        hero_cn = meta.get("cn") or hero.get("names", {}).get("cn")
        hero_en = meta.get("en") or hero.get("names", {}).get("en")
        hero_role = meta.get("role") or hero.get("role")
        timeline = hero.get("timeline", [])
        # standard-only search surface: special-mode records (April Fools,
        # experiments, hero trials, ...) must not pollute the entry history
        timeline = [rec for rec in timeline
                    if (rec.get("mode") or "standard") == "standard"]

        # hero itself is a searchable entry (overview of all its changes)
        edited = any(rec.get("patch") in edits for rec in timeline)
        entries.append({
            "key": f"hero::{slug}",
            "dimension": "hero",
            "kind": "hero",
            "hero_slug": slug,
            "hero_cn": hero_cn,
            "hero_en": hero_en,
            "hero_role": hero_role,
            "name_cn": hero_cn,
            "name_en": hero_en,
            "slug": slug,
            "variants": [],
            "count": len(timeline),
            "changes": merged_change_count(timeline, pair_map),
            "first_date": _min_date(timeline),
            "last_date": _max_date(timeline),
            "edited": edited,
        })

        groups: dict[str, dict] = {}
        for rec in timeline:
            key = entry_key(rec)
            if key is None:
                continue
            group = groups.setdefault(key, {"dimension": rec.get("dimension"), "records": []})
            group["records"].append(rec)
        for key, group in groups.items():
            records = group["records"]
            dim = group["dimension"]
            first = records[0]
            rec_slug = first.get("ability_slug") or first.get("perk_slug") or first.get("subject")
            rec = names.get(rec_slug) if rec_slug else None
            if dim == "hero_attr":
                subject = first.get("subject") or "other"
                name_cn = ATTR_CN.get(subject, subject)
                name_en = subject
                entry_variants: list[str] = []
            else:
                name_cn = (rec.get("name_cn") if rec else None) or (
                    first.get("ability_cn") or first.get("perk_cn"))
                name_en = (rec.get("name_en") if rec else None) or (
                    first.get("ability_en") or first.get("perk_en"))
                entry_variants = variants.get(rec_slug, []) if rec_slug else []
            entries.append({
                "key": f"{slug}::{key}",
                "dimension": dim,
                "kind": first.get("kind"),
                "hero_slug": slug,
                "hero_cn": hero_cn,
                "hero_en": hero_en,
                "hero_role": hero_role,
                "name_cn": name_cn,
                "name_en": name_en,
                "slug": rec_slug,
                "variants": entry_variants,
                "count": len(records),
                "changes": merged_change_count(records, pair_map),
                "first_date": _min_date(records),
                "last_date": _max_date(records),
                "edited": any(r.get("patch") in edits for r in records),
            })

    dim_index = {dim: i for i, dim in enumerate(DIM_ORDER)}
    entries.sort(key=lambda e: (dim_index.get(e["dimension"], 99), e["hero_slug"], e["slug"] or ""))
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "updated": updated,
        "entries": entries,
    }


def write_entries_index(data_dir: pathlib.Path, index: dict) -> None:
    with open(data_dir / "entries_index.json", "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)


def _min_date(records: list[dict]) -> str:
    dates = [r.get("date") for r in records if r.get("date")]
    return min(dates) if dates else ""


def _max_date(records: list[dict]) -> str:
    dates = [r.get("date") for r in records if r.get("date")]
    return max(dates) if dates else ""
