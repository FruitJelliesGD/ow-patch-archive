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


def all_months(fetcher: Fetcher) -> list[tuple[str, int, int]]:
    months: list[tuple[str, int, int]] = []
    for site in ("en", "cn"):
        for year, month in (fetcher.en_month_list() if site == "en" else fetcher.cn_month_list()):
            months.append((site, year, month))
    return months


def run_pipeline(
    data_dir: pathlib.Path,
    months: list[tuple[str, int, int]] | None = None,
    fetch: Fetcher | None = None,
) -> RunResult:
    """Fetch and persist patches; writes only changed patches and rebuilt hero files."""
    fetch = fetch or Fetcher()
    resolver = NameResolver()
    manifest = load_manifest(data_dir)
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
                print(f"WARN: fetch failed {site} {year}-{month:02d}: {exc}")
            continue
        result.fetched_months += 1
        parsed.extend(parse_patch_notes(page.html, site, url=page.url))

    report = detect_changes(parsed, manifest)
    result.events = report.events

    for event in report.events:
        patch = event.patch
        enrich_names(patch, resolver)
        result.unknown_heroes.extend(resolver.unknown_heroes)
        result.unknown_abilities.extend(resolver.unknown_abilities)
        resolver.unknown_heroes.clear()
        resolver.unknown_abilities.clear()

        old_dict = _load_patch_dict(data_dir, patch.site, patch.id) if event.kind == "modified" else {}
        if event.kind == "modified":
            event.diff_entries = deep_diff(old_dict, patch_to_dict(patch))
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
        append_changelog(data_dir, entry)

    if report.events:
        save_manifest(data_dir, manifest)
        build_hero_files(data_dir, resolver)

    return result


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


NON_HERO_NAMES = {"Items", "New Gadgets Added", "General Item Updates", "General Items", "General Updates"}


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
    resolver = resolver or NameResolver()

    for site_dir in ("en", "cn"):
        for patch_file in sorted((data_dir / "patches" / site_dir).glob("*.json")):
            data = json.loads(patch_file.read_text(encoding="utf-8"))
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
                        for change in ability.get("changes", []):
                            timeline.setdefault(slug, []).append({
                                "patch": data["id"], "date": data["date"], "site": data["site"],
                                "url": data.get("url"), "patch_title": data.get("title"),
                                "kind": "ability",
                                "ability_slug": ability.get("slug"),
                                "ability_en": ability.get("name_en"),
                                "ability_cn": ability.get("name_cn"),
                                **{k: change.get(k) for k in ("text_en", "text_cn", "before", "after", "metric")},
                            })
                    for perk in hero.get("perks", []):
                        timeline.setdefault(slug, []).append({
                            "patch": data["id"], "date": data["date"], "site": data["site"],
                            "url": data.get("url"), "patch_title": data.get("title"),
                            "kind": "perk",
                            "perk_en": perk.get("name_en"),
                            "perk_cn": perk.get("name_cn"),
                            "status": perk.get("status"),
                            "lines_en": perk.get("lines_en", []),
                            "lines_cn": perk.get("lines_cn", []),
                        })
                    for line in hero.get("general", []):
                        timeline.setdefault(slug, []).append({
                            "patch": data["id"], "date": data["date"], "site": data["site"],
                            "url": data.get("url"), "patch_title": data.get("title"),
                            "kind": "general",
                            "text_en": line if data["site"] == "en" else None,
                            "text_cn": line if data["site"] == "cn" else None,
                        })

    heroes_dir = data_dir / "heroes"
    heroes_dir.mkdir(parents=True, exist_ok=True)
    for slug, entries in timeline.items():
        entries.sort(key=lambda e: e["date"], reverse=True)
        with open(heroes_dir / f"{slug}.json", "w", encoding="utf-8") as fh:
            json.dump({"slug": slug, "names": {"en": meta[slug]["en"], "cn": meta[slug]["cn"]},
                       "role": meta[slug]["role"], "timeline": entries},
                      fh, ensure_ascii=False, indent=1)

    index = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "heroes": sorted(meta.values(), key=lambda h: h["slug"]),
    }
    with open(data_dir / "heroes_index.json", "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)

    # remove hero files whose slug no longer exists (slug corrections / filtered names)
    for stale in heroes_dir.glob("*.json"):
        if stale.stem not in meta:
            stale.unlink()


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
