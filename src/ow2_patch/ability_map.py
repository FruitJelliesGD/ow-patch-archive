"""Derive an EN<->CN ability/perk name map from paired patches.

The curated names.json only covers a handful of abilities; this module learns the
rest automatically: for every paired EN/CN patch and hero, ability/perk names are
aligned by position (CN mirrors EN layout) and aggregated into canonical slugs.
EN variant spellings ("Helix Rocket" vs "Helix Rockets") fold together via stem
comparison so a single history is kept per logical ability/perk.
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter, defaultdict

from .names import NameResolver, slugify


def _load_patch(data_dir: pathlib.Path, site: str, patch_id: str) -> dict:
    parts = patch_id.split("-")
    date = "-".join(parts[1:4])
    seq = parts[4]
    return json.loads((data_dir / "patches" / site / f"{date}-{seq}.json").read_text(encoding="utf-8"))


def _stem_slug(name: str) -> str:
    """slug with a trailing plural 's' stripped, used only for variant folding."""
    slug = slugify(name)
    return slug[:-1] if slug.endswith("s") else slug


def _find_cn_hero(cn_patch: dict, hero_slug: str) -> dict | None:
    for section in cn_patch.get("sections", []):
        for hero in section.get("heroes", []):
            if hero.get("slug") == hero_slug:
                return hero
    return None


def _pick_canonical(en_counter: Counter, resolver: NameResolver) -> str:
    """Most frequent EN name, preferring names.json entries."""
    ranked = sorted(en_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    for name, _ in ranked:
        if resolver.ability(name, "en")[1]:
            return name
    return ranked[0][0] if ranked else ""


def build_ability_map(data_dir: pathlib.Path, pairs: list[dict],
                      resolver: NameResolver | None = None,
                      weapons: dict | None = None) -> dict:
    resolver = resolver or NameResolver(data_dir / "names.json")
    if weapons is None:
        from .weapons import load_weapons

        weapons = load_weapons(data_dir / "weapons.json")

    ability_pairs: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    perk_pairs: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    en_abilities: dict[str, Counter] = defaultdict(Counter)
    en_perks: dict[str, Counter] = defaultdict(Counter)

    # EN-only patches (OW1 era etc.) still contribute spelling variants
    for patch_file in sorted((data_dir / "patches" / "en").glob("*.json")):
        patch = json.loads(patch_file.read_text(encoding="utf-8"))
        for section in patch.get("sections", []):
            for hero in section.get("heroes", []):
                hero_slug = hero.get("slug")
                if not hero_slug:
                    continue
                for item in hero.get("abilities", []):
                    if item.get("name_en"):
                        en_abilities[hero_slug][item["name_en"]] += 1
                for item in hero.get("perks", []):
                    if item.get("name_en"):
                        en_perks[hero_slug][item["name_en"]] += 1

    for pair in pairs:
        en_patch = _load_patch(data_dir, "en", pair["en"]["patch_id"])
        cn_patch = _load_patch(data_dir, "cn", pair["cn"]["patch_id"])
        for section in en_patch.get("sections", []):
            for en_hero in section.get("heroes", []):
                hero_slug = en_hero.get("slug")
                if not hero_slug:
                    continue
                cn_hero = _find_cn_hero(cn_patch, hero_slug)
                cn_abilities = cn_hero.get("abilities", []) if cn_hero else []
                cn_perks = cn_hero.get("perks", []) if cn_hero else []
                for en_item, cn_item in zip(en_hero.get("abilities", []), cn_abilities):
                    en_name = en_item.get("name_en") or ""
                    cn_name = cn_item.get("name_cn") or ""
                    if en_name:
                        en_abilities[hero_slug][en_name] += 1
                    if en_name and cn_name:
                        ability_pairs[hero_slug][cn_name][en_name] += 1
                for en_item, cn_item in zip(en_hero.get("perks", []), cn_perks):
                    en_name = en_item.get("name_en") or ""
                    cn_name = cn_item.get("name_cn") or ""
                    if en_name:
                        en_perks[hero_slug][en_name] += 1
                    if en_name and cn_name:
                        perk_pairs[hero_slug][cn_name][en_name] += 1

    abilities, abilities_by_cn, abilities_by_en = _aggregate(
        ability_pairs, en_abilities, resolver)
    perks, perks_by_cn, perks_by_en = _aggregate(perk_pairs, en_perks, resolver)
    _label_weapon_kinds(abilities, weapons)

    return {
        "abilities": dict(sorted(abilities.items())),
        "by_cn": dict(abilities_by_cn),
        "by_en": dict(sorted(abilities_by_en.items())),
        "perks": dict(sorted(perks.items())),
        "perks_by_cn": dict(perks_by_cn),
        "perks_by_en": dict(sorted(perks_by_en.items())),
        "unresolved": [],
    }


def _label_weapon_kinds(abilities: dict, weapons: dict) -> None:
    """Tag each ability entry with kind=weapon|ability (seed table first, then roots)."""
    from .weapons import classify_ability

    for slug, entry in abilities.items():
        entry["kind"] = classify_ability(entry.get("name_en") or "",
                                         entry.get("name_cn") or "",
                                         entry["heroes"][0] if entry.get("heroes") else "",
                                         weapons)


def _aggregate(pairs: dict, en_seen: dict, resolver: NameResolver):
    entries: dict[str, dict] = {}
    by_cn: dict[str, list[str]] = defaultdict(list)
    by_en: dict[str, str] = {}

    def register(hero: str, cn_name: str, en_name: str) -> str:
        canonical = _pick_canonical(pairs[hero].get(cn_name, Counter()), resolver) or en_name
        slug = slugify(canonical)
        entry = entries.setdefault(slug, {
            "heroes": [], "name_en": canonical, "name_cn": cn_name,
            "cn_variants": [], "en_variants": [], "weak": False,
        })
        if hero not in entry["heroes"]:
            entry["heroes"].append(hero)
        if cn_name not in entry["cn_variants"]:
            entry["cn_variants"].append(cn_name)
        for name in (canonical, en_name):
            if name and name not in entry["en_variants"]:
                entry["en_variants"].append(name)
        if slug not in by_cn[cn_name]:
            by_cn[cn_name].append(slug)
        by_en[en_name] = slug
        return slug

    # strong signals: names that were seen on both sides of a pair
    for hero, cn_names in pairs.items():
        for cn_name, en_counter in cn_names.items():
            canonical = _pick_canonical(en_counter, resolver)
            register(hero, cn_name, canonical)

    # fold variant spellings (incl. EN-only names) into canonical entries.
    # slug_to_canonical maps every seen variant slug (and its singular stem) to the
    # canonical slug, so "Helix Rockets" and "Helix Rocket" share one history.
    slug_to_canonical: dict[str, str] = {}
    for slug in entries:
        slug_to_canonical[slug] = slug
        slug_to_canonical.setdefault(_stem_slug(slug), slug)

    for hero, names in en_seen.items():
        for en_name in names:
            if en_name in by_en:
                continue
            slug = slugify(en_name)
            stem = _stem_slug(en_name)
            target = slug_to_canonical.get(slug) or slug_to_canonical.get(stem)
            if target is None:
                target = resolver.ability(en_name, "en")[0]
                entries.setdefault(target, {
                    "heroes": [hero], "name_en": en_name, "name_cn": None,
                    "cn_variants": [], "en_variants": [], "weak": True,
                })
                slug_to_canonical[target] = target
                slug_to_canonical.setdefault(_stem_slug(en_name), target)
            if en_name not in entries[target]["en_variants"]:
                entries[target]["en_variants"].append(en_name)
            if hero not in entries[target]["heroes"]:
                entries[target]["heroes"].append(hero)
            by_en[en_name] = target

    for entry in entries.values():
        entry["heroes"].sort()
        entry["cn_variants"] = sorted(set(cn for cn in entry["cn_variants"] if cn))
        entry["en_variants"] = list(dict.fromkeys(entry["en_variants"]))
    for cn_name, slugs in by_cn.items():
        by_cn[cn_name] = list(dict.fromkeys(slugs))
    return entries, by_cn, by_en


def write_ability_map(data_dir: pathlib.Path, ability_map: dict) -> None:
    with open(data_dir / "ability_map.json", "w", encoding="utf-8") as fh:
        json.dump(ability_map, fh, ensure_ascii=False, indent=1)
