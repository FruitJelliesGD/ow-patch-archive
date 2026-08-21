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

DIM_ORDER = ["weapon", "ability", "perk", "hero_attr", "hero"]

# Mirrors web/app.js ATTR_LABEL (hero-attribute display names).
ATTR_CN = {
    "health": "生命值",
    "ultimate_cost": "终极技能消耗",
    "move_speed": "移动速度",
    "base_stat": "基础属性",
    "other": "其他",
}


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
    return {"updated": updated, "edits": edits}


def write_official_edits(data_dir: pathlib.Path, edits: dict) -> None:
    with open(data_dir / "official_edits.json", "w", encoding="utf-8") as fh:
        json.dump(edits, fh, ensure_ascii=False, indent=1)


def build_entries_index(data_dir: pathlib.Path, official_edits: dict | None = None) -> dict:
    """Flat search index of every searchable entry across all heroes."""
    edits = (official_edits or {}).get("edits", {})

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
                "first_date": _min_date(records),
                "last_date": _max_date(records),
                "edited": any(r.get("patch") in edits for r in records),
            })

    dim_index = {dim: i for i, dim in enumerate(DIM_ORDER)}
    entries.sort(key=lambda e: (dim_index.get(e["dimension"], 99), e["hero_slug"], e["slug"] or ""))
    return {"updated": updated, "entries": entries}


def write_entries_index(data_dir: pathlib.Path, index: dict) -> None:
    with open(data_dir / "entries_index.json", "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)


def _min_date(records: list[dict]) -> str:
    dates = [r.get("date") for r in records if r.get("date")]
    return min(dates) if dates else ""


def _max_date(records: list[dict]) -> str:
    dates = [r.get("date") for r in records if r.get("date")]
    return max(dates) if dates else ""
