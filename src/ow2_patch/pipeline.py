"""Orchestration: fetch months -> parse -> diff -> enrich names -> persist data + heroes.

The content hash is computed on the raw parse (before name enrichment) so that edits
to data/names.json never masquerade as official patch modifications.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .diff import (
    ChangeEvent,
    append_changelog,
    deep_diff,
    detect_changes,
    is_cosmetic_diff,
    load_manifest,
    patch_hash,
    save_manifest,
)
from .fetch import Fetcher
from .model import Patch, patch_to_dict
from .names import NameResolver
from .parse import parse_patch_notes
from .render import render_md


@dataclass
class RunResult:
    fetched_months: int = 0
    events: list[ChangeEvent] = field(default_factory=list)
    unknown_heroes: list[tuple[str, str]] = field(default_factory=list)
    unknown_abilities: list[tuple[str, str]] = field(default_factory=list)
    # non-404 fetch failures: (site, year, month, error) — recorded so callers
    # can fail loudly (--fail-on-error) instead of silently reporting 0 changes
    fetch_errors: list[tuple[str, int, int, str]] = field(default_factory=list)


def all_months(fetcher: Fetcher) -> list[tuple[str, int, int]]:
    months: list[tuple[str, int, int]] = []
    for site in ("en", "cn"):
        for year, month in (fetcher.en_month_list() if site == "en" else fetcher.cn_month_list()):
            months.append((site, year, month))
    return months


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def is_cn_variant_drift(patches: list[Patch]) -> bool:
    """True when a CN month page is served in the internationalized variant.

    ow.blizzard.cn returns Chinese hero/ability names to CN IPs but an
    English-named variant to foreign IPs (the GitHub runner is US-based).
    Detected by the fraction of hero names without any CJK characters;
    Chinese-named pages keep >50% CJK names, the English variant flips it.
    """
    names = [h.name_cn or h.name_en
             for p in patches for s in p.sections for h in s.heroes]
    names = [n for n in names if n]
    if len(names) < 5:
        return False  # too little signal (e.g. a generic-update month)
    latin = sum(1 for n in names if not _has_cjk(n))
    return latin / len(names) > 0.5


def run_pipeline(
    data_dir: pathlib.Path,
    months: list[tuple[str, int, int]] | None = None,
    fetch: Fetcher | None = None,
    force_rewrite: bool = False,
) -> RunResult:
    """Fetch and persist patches; writes only changed patches and rebuilt hero files.

    force_rewrite bypasses change detection: every parsed patch is re-enriched and
    re-persisted (JSON + Markdown) with its manifest hash refreshed, without
    changelog entries or diffs. Used for one-time format migrations after a
    parser change; the manifest hash stays stable for the same parser output.
    """
    fetch = fetch or Fetcher()
    resolver = NameResolver(data_dir / "names.json")
    manifest = load_manifest(data_dir)
    from .diff import ensure_hash_schema, patch_hash

    ensure_hash_schema(data_dir, manifest)
    result = RunResult()

    if months is None:
        months = all_months(fetch)

    parsed: list[Patch] = []
    for site, year, month in months:
        try:
            page = fetch.fetch_month(site, year, month)
        except Exception as exc:
            # 404 (CN 无补丁月份) is expected; anything else should be visible in logs
            if "404" not in str(exc):
                result.fetch_errors.append((site, year, month, str(exc)))
                print(f"WARN: fetch failed {site} {year}-{month:02d}: {exc}")
            continue
        result.fetched_months += 1
        month_patches = parse_patch_notes(page.html, site, url=page.url, resolver=resolver)
        if site == "cn" and is_cn_variant_drift(month_patches):
            # ow.blizzard.cn serves an internationalized (English-named) variant
            # to non-CN IPs; the GitHub runner would otherwise re-archive every
            # CN patch with English hero names. Skip and keep the Chinese archive.
            print(f"WARN: cn {year}-{month:02d} served the international variant "
                  f"(English hero names); skipping {len(month_patches)} patches")
            continue
        parsed.extend(month_patches)

    if force_rewrite:
        for patch in parsed:
            _enrich(patch, resolver, result)
            patch.hash = patch_hash(patch)
            _write_patch(data_dir, patch)
            manifest[patch.id] = {
                "hash": patch.hash,
                "site": patch.site,
                "date": patch.date,
                "title": patch.title,
                "url": patch.url,
            }
        save_manifest(data_dir, manifest)
        regenerate_all(data_dir)
        return result

    report = detect_changes(parsed, manifest)
    result.events = report.events

    for event in report.events:
        patch = event.patch
        _enrich(patch, resolver, result)

        old_dict = _load_patch_dict(data_dir, patch.site, patch.id) if event.kind == "modified" else {}
        if event.kind == "modified":
            new_dict = patch_to_dict(patch)
            event.diff_entries = deep_diff(old_dict, new_dict)
            event.cosmetic = is_cosmetic_diff(event.diff_entries, old_dict, new_dict)
        _write_patch(data_dir, patch)
        manifest[patch.id] = {
            "hash": patch.hash,
            "site": patch.site,
            "date": patch.date,
            "title": patch.title,
            "url": patch.url,
        }
        entry: dict = {
            "kind": event.kind,
            "patch_id": patch.id,
            "site": patch.site,
            "date": patch.date,
            "title": patch.title,
            "url": patch.url,
        }
        if event.kind == "modified":
            entry["diff"] = [
                {"path": d.path, "old": d.old, "new": d.new}
                for d in event.diff_entries
            ]
            if event.cosmetic:
                entry["cosmetic"] = True
        append_changelog(data_dir, entry)

    if report.events:
        save_manifest(data_dir, manifest)
        regenerate_all(data_dir)

    return result


def _enrich(patch: Patch, resolver: NameResolver, result: RunResult) -> None:
    enrich_names(patch, resolver)
    result.unknown_heroes.extend(resolver.unknown_heroes)
    result.unknown_abilities.extend(resolver.unknown_abilities)
    resolver.unknown_heroes.clear()
    resolver.unknown_abilities.clear()


def regenerate_all(data_dir: pathlib.Path) -> None:
    """Full offline regeneration, in dependency order:

    reclassify -> extraction -> attribution -> re-enrich -> pair -> ability map
    (with weapon kinds) -> hash schema migration -> hero timelines (+ value series).

    Pure pass over data/ (no network). Used by the pipeline after any patch write
    and by tools/rebuild.py for the whole archive.
    """
    from .ability_map import build_ability_map, write_ability_map
    from .attribution import classify_general, fix_hash_slugs
    from .diff import ensure_hash_schema, load_manifest
    from .entries import build_entries_index, build_official_edits, write_entries_index, write_official_edits
    from .extract import apply_extraction
    from .normalize import reclassify_patch_dict, split_merged_perk_general
    from .pairing import build_patches_index, pair_patches, patch_meta_from_manifest, write_pair_result

    resolver = NameResolver(data_dir / "names.json")
    for site_dir in ("en", "cn"):
        for patch_file in (data_dir / "patches" / site_dir).glob("*.json"):
            data = json.loads(patch_file.read_text(encoding="utf-8"))
            reclassify_patch_dict(data)
            split_merged_perk_general(data)
            for section in data.get("sections", []):
                for hero in section.get("heroes", []):
                    for ability in hero.get("abilities", []):
                        for change in ability.get("changes", []):
                            apply_extraction(change)
            _reenrich_dict(data, resolver)
            patch_file.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    en, cn = patch_meta_from_manifest(data_dir)
    pair_result = pair_patches(en, cn)
    write_pair_result(data_dir, pair_result)
    build_patches_index(data_dir, pair_result)

    ability_map = build_ability_map(data_dir, pair_result.pairs, resolver)
    write_ability_map(data_dir, ability_map)

    # attribution moves general lines into abilities/perks (needs the ability map)
    for site_dir in ("en", "cn"):
        for patch_file in (data_dir / "patches" / site_dir).glob("*.json"):
            data = json.loads(patch_file.read_text(encoding="utf-8"))
            classify_general(data, resolver, ability_map)
            fix_hash_slugs(data, resolver, ability_map)
            patch_file.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # map reflects the post-attribution data (bracket-attached abilities included)
    ability_map = build_ability_map(data_dir, pair_result.pairs, resolver)
    write_ability_map(data_dir, ability_map)

    ensure_hash_schema(data_dir, load_manifest(data_dir))

    build_hero_files(data_dir, NameResolver(data_dir / "names.json"))

    edits = build_official_edits(data_dir)
    write_official_edits(data_dir, edits)
    write_entries_index(data_dir, build_entries_index(data_dir, edits))


def _reenrich_dict(data: dict, resolver: NameResolver) -> None:
    for section in data.get("sections", []):
        for hero in section.get("heroes", []):
            if hero.get("name_en"):
                slug, en, cn, role = resolver.hero(hero["name_en"], "en")
            elif hero.get("name_cn"):
                slug, en, cn, role = resolver.hero(hero["name_cn"], "cn")
            else:
                continue
            hero["slug"] = slug
            hero["name_en"] = en or hero.get("name_en")
            hero["name_cn"] = cn or hero.get("name_cn")
            if not hero.get("role"):
                hero["role"] = role
            for ability in hero.get("abilities", []):
                if ability.get("name_en"):
                    aslug, aen, acn = resolver.ability(ability["name_en"], "en", slug)
                elif ability.get("name_cn"):
                    aslug, aen, acn = resolver.ability(ability["name_cn"], "cn", slug)
                else:
                    continue
                ability["slug"] = aslug
                ability["name_en"] = aen or ability.get("name_en")
                ability["name_cn"] = acn or ability.get("name_cn")


def enrich_names(patch: Patch, resolver: NameResolver) -> None:
    """Fill hero/ability slugs and cross-language names from the mapping table."""
    for section in patch.sections:
        for hero in section.heroes:
            if hero.name_en:
                slug, en, cn, role = resolver.hero(hero.name_en, "en")
            elif hero.name_cn:
                slug, en, cn, role = resolver.hero(hero.name_cn, "cn")
            else:
                continue
            hero.slug = slug
            hero.name_en = en or hero.name_en
            hero.name_cn = cn or hero.name_cn
            if hero.role is None:
                hero.role = role
            for ability in hero.abilities:
                if ability.name_en:
                    aslug, aen, acn = resolver.ability(ability.name_en, "en")
                elif ability.name_cn:
                    aslug, aen, acn = resolver.ability(ability.name_cn, "cn")
                else:
                    continue
                ability.slug = aslug
                ability.name_en = aen or ability.name_en
                ability.name_cn = acn or ability.name_cn


def _write_patch(data_dir: pathlib.Path, patch: Patch) -> None:
    patches_dir = data_dir / "patches" / patch.site
    archive_dir = data_dir / "archive" / patch.site / patch.date[:4] / patch.date[5:7]
    patches_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{patch.date}-{patch.seq}"
    with open(patches_dir / f"{stem}.json", "w", encoding="utf-8") as fh:
        json.dump(patch_to_dict(patch), fh, ensure_ascii=False, indent=1)
    with open(archive_dir / f"{stem}.md", "w", encoding="utf-8") as fh:
        fh.write(render_md(patch))


def _load_patch_dict(data_dir: pathlib.Path, site: str, patch_id: str) -> dict:
    parts = patch_id.split("-")
    date = "-".join(parts[1:4])
    seq = parts[4]
    path = data_dir / "patches" / site / f"{date}-{seq}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


NON_HERO_NAMES = {"Items", "New Gadgets Added", "General Item Updates", "General Items",
                  "General Updates", "综合物品", "新增装置", "物品"}


def _is_balance_hero(hero: dict) -> bool:
    """Stadium cosmetic blocks (e.g. 'Ramattra Mask' / '“士兵：76”面具') are not balance changes."""
    name = hero.get("name_en") or hero.get("name_cn") or ""
    if name.endswith(" Mask") or name.endswith("面具") or name in NON_HERO_NAMES:
        return False
    return True


def build_hero_files(data_dir: pathlib.Path, resolver: NameResolver | None = None) -> None:
    """Rebuild heroes/{slug}.json timelines and heroes_index.json from stored patches."""
    timeline: dict[str, list[dict]] = {}
    meta: dict[str, dict] = {}
    resolver = resolver or NameResolver(data_dir / "names.json")
    ability_kinds: dict[str, str] = {}
    ability_map_path = data_dir / "ability_map.json"
    if ability_map_path.exists():
        ability_map = json.loads(ability_map_path.read_text(encoding="utf-8"))
        ability_kinds = {slug: entry.get("kind", "ability")
                         for slug, entry in ability_map.get("abilities", {}).items()}

    # authoritative patch-level mode (pair-level: either side non-standard wins);
    # every patch id appears in patches_index, so the map is complete when present
    from .modes import patch_mode_with_sections

    mode_by_patch: dict[str, str] = {}
    index_path = data_dir / "patches_index.json"
    if index_path.exists():
        for p in json.loads(index_path.read_text(encoding="utf-8")).get("patches", []):
            m = p.get("mode") or "standard"
            if p.get("patch_id_en"):
                mode_by_patch[p["patch_id_en"]] = m
            if p.get("patch_id_cn"):
                mode_by_patch[p["patch_id_cn"]] = m

    for site_dir in ("en", "cn"):
        for patch_file in sorted((data_dir / "patches" / site_dir).glob("*.json")):
            data = json.loads(patch_file.read_text(encoding="utf-8"))
            mode = mode_by_patch.get(data["id"]) or patch_mode_with_sections(
                data.get("title") or "",
                [s.get("title") or "" for s in data.get("sections", [])])
            for section in data.get("sections", []):
                for hero in section.get("heroes", []):
                    if not _is_balance_hero(hero):
                        continue
                    slug = hero.get("slug") or _fallback_slug(hero, resolver)
                    meta.setdefault(slug, {
                        "slug": slug,
                        "en": hero.get("name_en"),
                        "cn": hero.get("name_cn"),
                        "role": hero.get("role") or _canonical_role(hero, resolver),
                    })
                    for ability in hero.get("abilities", []):
                        if not (ability.get("name_en") or ability.get("name_cn")):
                            continue  # nameless artifact entries
                        a_name = ability.get("name_en") or ability.get("name_cn") or ""
                        a_site = "en" if ability.get("name_en") else "cn"
                        a_slug = ability.get("slug") or resolver.ability(a_name, a_site, slug)[0]
                        a_dim = ability_kinds.get(a_slug, "ability")
                        for change in ability.get("changes", []):
                            timeline.setdefault(slug, []).append({
                                "patch": data["id"], "date": data["date"], "site": data["site"],
                                "url": data.get("url"), "patch_title": data.get("title"),
                                "kind": "ability",
                                "dimension": a_dim,
                                "mode": mode,
                                "ability_slug": a_slug,
                                "ability_en": ability.get("name_en"),
                                "ability_cn": ability.get("name_cn"),
                                **{k: change.get(k) for k in ("text_en", "text_cn", "before", "after", "by", "by_pct", "metric", "unit")},
                            })
                    for perk in hero.get("perks", []):
                        p_name = perk.get("name_en") or perk.get("name_cn") or ""
                        p_site = "en" if perk.get("name_en") else "cn"
                        p_slug = resolver.perk(p_name, p_site, slug)[0] if p_name else "perk"
                        perk_numbers = _perk_numbers(perk, p_site)
                        timeline.setdefault(slug, []).append({
                            "patch": data["id"], "date": data["date"], "site": data["site"],
                            "url": data.get("url"), "patch_title": data.get("title"),
                            "kind": "perk",
                            "dimension": "perk",
                            "mode": mode,
                            "perk_slug": p_slug,
                            "perk_en": perk.get("name_en"),
                            "perk_cn": perk.get("name_cn"),
                            "status": perk.get("status"),
                            "lines_en": perk.get("lines_en", []),
                            "lines_cn": perk.get("lines_cn", []),
                            **perk_numbers,
                        })
                    for line in hero.get("general", []):
                        entry_text = line if isinstance(line, str) else (
                            line.get("text_en") or line.get("text_cn") or "")
                        if not entry_text:
                            continue
                        timeline.setdefault(slug, []).append({
                            "patch": data["id"], "date": data["date"], "site": data["site"],
                            "url": data.get("url"), "patch_title": data.get("title"),
                            "kind": "general",
                            "dimension": line.get("dimension") if isinstance(line, dict) else None,
                            "subject": line.get("subject") if isinstance(line, dict) else None,
                            "mode": mode,
                            "text_en": entry_text if data["site"] == "en" else None,
                            "text_cn": entry_text if data["site"] == "cn" else None,
                            **{k: line.get(k) for k in ("before", "after", "by", "by_pct", "metric", "unit")
                               if isinstance(line, dict)},
                        })
                    for item in hero.get("stadium_items", []):
                        # Stadium item lines stay in the hero timeline as general
                        # entries (their pre-structured shape), so the timeline
                        # content is unchanged by the structuring
                        for iline in item.get("lines_en", []) + item.get("lines_cn", []):
                            if not iline:
                                continue
                            timeline.setdefault(slug, []).append({
                                "patch": data["id"], "date": data["date"], "site": data["site"],
                                "url": data.get("url"), "patch_title": data.get("title"),
                                "kind": "general",
                                "dimension": None,
                                "subject": None,
                                "mode": mode,
                                "text_en": iline if data["site"] == "en" else None,
                                "text_cn": iline if data["site"] == "cn" else None,
                            })

    heroes_dir = data_dir / "heroes"
    heroes_dir.mkdir(parents=True, exist_ok=True)
    from .values import build_values

    for slug, entries in timeline.items():
        entries.sort(key=lambda e: e["date"], reverse=True)
        with open(heroes_dir / f"{slug}.json", "w", encoding="utf-8") as fh:
            json.dump({"slug": slug, "names": {"en": meta[slug]["en"], "cn": meta[slug]["cn"]},
                       "role": meta[slug]["role"], "timeline": entries,
                       # value series are standard-only: special-mode numbers must
                       # not pollute the balance history (frontend shows all records
                       # on toggle, but chips stay standard)
                       "values": build_values([e for e in entries if e["mode"] == "standard"])},
                      fh, ensure_ascii=False, indent=1)

    latest = "2016-05-01"
    for site_dir in ("en", "cn"):
        for patch_file in (data_dir / "patches" / site_dir).glob("*.json"):
            try:
                patch_data = json.loads(patch_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if patch_data.get("date", "") > latest:
                latest = patch_data["date"]
    index = {
        "updated": f"{latest}T00:00:00Z",
        "heroes": sorted(meta.values(), key=lambda h: h["slug"]),
    }
    with open(data_dir / "heroes_index.json", "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)

    # remove hero files whose slug no longer exists (slug corrections / filtered names)
    for stale in heroes_dir.glob("*.json"):
        if stale.stem not in meta:
            stale.unlink()


def _perk_numbers(perk: dict, site: str) -> dict:
    """Best-effort numeric fields from the first parseable perk line."""
    from .extract import extract_change

    lines = perk.get("lines_en") if site == "en" else perk.get("lines_cn")
    for line in lines or []:
        result = extract_change(line, site)
        if result.before is not None or result.by_pct is not None:
            return {
                "before": result.before, "after": result.after,
                "by": result.by, "by_pct": result.by_pct,
                "metric": result.metric, "unit": result.unit,
            }
    return {}


def _fallback_slug(hero: dict, resolver: NameResolver) -> str:
    name = hero.get("name_en") or hero.get("name_cn") or "unknown"
    site = "en" if hero.get("name_en") else "cn"
    return resolver.hero(name, site)[0]


def _canonical_role(hero: dict, resolver: NameResolver) -> str | None:
    if hero.get("name_en"):
        return resolver.hero(hero["name_en"], "en")[3]
    if hero.get("name_cn"):
        return resolver.hero(hero["name_cn"], "cn")[3]
    return None
