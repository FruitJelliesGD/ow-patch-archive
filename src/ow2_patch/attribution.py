"""Attribution and classification of hero.general entries (offline rebuild pass).

Turns free-text general lines into structured entries and re-attaches the ones that
belong to a known ability/perk:

  1. "[Weapon/Ability] ..." bracket-prefixed lines -> the ability's changes
  2. "Name - Power" / "名——异能" perk-name leaks -> perk entries
  3. remaining lines -> dict entries classified as hero attributes (health /
     ultimate cost / move speed / base stat) or `other`, with numeric fields
     extracted where possible.

Text is never dropped: unresolved lines stay in general with their original text.
"""

from __future__ import annotations

import re

from .extract import extract_change

_BRACKET_RE = re.compile(r"^\[([^\]\[]+)\](.*)$")
_PERK_NAME_RE = re.compile(
    r"^(.*?)\s*-\s*Power$|^(.*?)——(?:主要|次级)?(?:威能|异能)$"
)
_PERK_WITH_BODY_RE = re.compile(
    r"^(.*?)\s*-\s*Power\s+(.+)$|^(.*?)——(?:主要|次级)?(?:威能|异能)\s+(.+)$|^(Minor|Major) Perk\s*[-–]\s*(.+)$"
)

_ATTR_RULES = [
    ("health", ("生命值", "生命上限", "health", "护甲", "armor", "overhealth", "过量生命值")),
    ("ultimate_cost", ("终极技能消耗", "ultimate cost", "ultimate charge", "终极技能充能")),
    ("move_speed", ("移动速度", "movement speed", "移速")),
    ("base_stat", ("基础伤害", "基础射速", "base damage", "base stat", "基础生命")),
]


def classify_general(data: dict, resolver, ability_map: dict) -> int:
    """Rewrite every hero.general list in a patch dict; returns entries attributed away."""
    moved = 0
    for section in data.get("sections", []):
        for hero in section.get("heroes", []):
            hero_slug = hero.get("slug") or ""
            general = hero.get("general", [])
            kept: list = []
            for entry in general:
                text = entry if isinstance(entry, str) else (
                    entry.get("text_en") or entry.get("text_cn") or "")
                if not text:
                    continue
                site = "en" if data.get("site") == "en" else "cn"
                if _BRACKET_RE.match(text):
                    if _attach_bracket(hero, text, site, hero_slug, resolver, ability_map):
                        moved += 1
                        continue
                perk_name = _perk_name_line(text)
                if perk_name:
                    _attach_perk(hero, text, perk_name, site)
                    moved += 1
                    continue
                kept.append(_classify_attr(text, site))
            hero["general"] = kept
    return moved


def _attach_bracket(hero: dict, text: str, site: str, hero_slug: str,
                    resolver, ability_map: dict) -> bool:
    m = _BRACKET_RE.match(text)
    name = m.group(1).strip()
    body = m.group(2).strip()
    slug = _resolve_ability(name, site, hero_slug, resolver, ability_map)
    if slug is None:
        return False
    change = {"text_en": text if site == "en" else None,
              "text_cn": text if site == "cn" else None}
    _apply_extracted(change, text, site)
    for ability in hero.get("abilities", []):
        if ability.get("slug") == slug:
            ability.setdefault("changes", []).append(change)
            return True
    hero.setdefault("abilities", []).append({
        "name_en": None if site == "cn" else name,
        "name_cn": None if site == "en" else name,
        "slug": slug,
        "changes": [change],
    })
    return True


def _resolve_ability(name: str, site: str, hero_slug: str,
                     resolver, ability_map: dict) -> str | None:
    """Resolve a bracket-prefixed ability name; None means 'cannot attribute'."""
    slug, en, cn = resolver.ability(name, site, hero_slug)
    resolved = False
    if site == "en":
        resolved = (name in ability_map.get("by_en", {})) or (cn is not None)
    else:
        resolved = (name in ability_map.get("by_cn", {})) or (en is not None)
    if resolved and slug and not slug.startswith("hero-"):
        entry = ability_map.get("abilities", {}).get(slug)
        if entry and hero_slug not in entry.get("heroes", []):
            return None
        return slug
    # abbreviated names ("脉冲步枪" inside "重脉冲步枪"): substring match
    index = ability_map.get("by_cn" if site == "cn" else "by_en", {})
    for key, slugs in index.items():
        if name and (name in key or key in name):
            for candidate in slugs:
                entry = ability_map.get("abilities", {}).get(candidate, {})
                if hero_slug in entry.get("heroes", []):
                    return candidate
    return None


def _perk_name_line(text: str) -> str | None:
    m = _PERK_WITH_BODY_RE.match(text.strip())
    if m:
        return (m.group(1) or m.group(3) or m.group(5) or "").strip()
    m = _PERK_NAME_RE.match(text.strip())
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").strip()


def _attach_perk(hero: dict, text: str, perk_name: str, site: str) -> None:
    """Attach a general line to a perk entry.

    The original full line is always preserved in `raw_text` (or merged into the
    lines list when it carries a body), so the content text bag stays identical to
    a fresh parse — attribution must never drop or rewrite original text.
    """
    body = ""
    m = _PERK_WITH_BODY_RE.match(text.strip())
    if m:
        body = (m.group(2) or m.group(4) or m.group(6) or "").strip()
    if site == "en":
        lines_en = [body] if body else []
        lines_cn = []
        raw = text
    else:
        lines_cn = [body] if body else []
        lines_en = []
        raw = text
    for perk in hero.get("perks", []):
        existing = perk.get("name_en") or perk.get("name_cn") or ""
        if existing == perk_name:
            if site == "en":
                perk.setdefault("lines_en", []).extend(lines_en)
            else:
                perk.setdefault("lines_cn", []).extend(lines_cn)
            perk.setdefault("raw_text", []).append(raw)
            return
    hero.setdefault("perks", []).append({
        "name_en": perk_name if site == "en" else None,
        "name_cn": perk_name if site == "cn" else None,
        "status": "changed",
        "lines_en": lines_en,
        "lines_cn": lines_cn,
        "raw_text": [raw],
    })


def fix_hash_slugs(data: dict, resolver, ability_map: dict) -> int:
    """Re-resolve hero-* hash-slug ability blocks against the ability map.

    Self-healing for blocks that were attached before their canonical slug was
    known (e.g. bracket-attributed names). Returns number of slugs repaired.
    """
    fixed = 0
    for section in data.get("sections", []):
        for hero in section.get("heroes", []):
            hero_slug = hero.get("slug") or ""
            site = "en" if data.get("site") == "en" else "cn"
            for ability in hero.get("abilities", []):
                if not (ability.get("slug") or "").startswith("hero-"):
                    continue
                name = ability.get("name_en") or ability.get("name_cn") or ""
                new_slug = _resolve_ability(name, site, hero_slug, resolver, ability_map)
                if new_slug:
                    ability["slug"] = new_slug
                    fixed += 1
    return fixed


def _classify_attr(text: str, site: str) -> dict:
    entry = {"text_en": text if site == "en" else None,
             "text_cn": text if site == "cn" else None}
    subject = None
    lower = text.lower()
    for name, keywords in _ATTR_RULES:
        if any(k.lower() in lower for k in keywords):
            subject = name
            break
    entry["subject"] = subject
    entry["dimension"] = "hero_attr" if subject else "other"
    _apply_extracted(entry, text, site)
    return entry


def _apply_extracted(entry: dict, text: str, site: str) -> None:
    result = extract_change(text, site)
    for field in ("before", "after", "by", "by_pct", "metric", "unit"):
        entry[field] = getattr(result, field)
