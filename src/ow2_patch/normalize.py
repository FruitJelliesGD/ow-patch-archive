"""Reclassify misclassified patch data: perk-shaped ability entries and merged
perk strings inside general lines become proper perk entries.

Some patch pages list perks under the abilities list ("Hyper Regeneration – Minor
Perk") or squash "name——威能 description…" into a single general line (CN 2026-06-17
style). These are normalized here so the hero timeline groups them as perks.
"""

from __future__ import annotations

import re

_EN_SUFFIX_RE = re.compile(r"^(.*?)\s*[-–]\s*(Minor|Major) Perk$", re.I)
_EN_PREFIX_RE = re.compile(r"^(Minor|Major) Perk\s*[-–]?\s*(.*)$", re.I)
_CN_SUFFIX_RE = re.compile(r"^(.*?)——(主要|次级)威能$")
_CN_MERGED_RE = re.compile(r"^(.+?)——(主要|次级)威能\s+(.+)$")
_CN_PREFIX_RE = re.compile(r"^(主要|次级)威能\s*[:：]?\s*(.*)$")

_ADDED = {"New", "Added", "新增", "已添加", "新加入", "添加"}
_REMOVED = {"Removed", "已移除", "移除"}
_MOVED = {"Moved", "改为了", "改为"}


def _perk_shape(name: str) -> tuple[str | None, bool]:
    """Return (stripped perk name, is_perk) for a display name."""
    if not name:
        return None, False
    m = _EN_SUFFIX_RE.match(name)
    if m:
        return m.group(1).strip(), True
    m = _EN_PREFIX_RE.match(name)
    if m:
        return m.group(2).strip() or m.group(1), True
    m = _CN_SUFFIX_RE.match(name)
    if m:
        return m.group(1).strip(), True
    m = _CN_PREFIX_RE.match(name)
    if m:
        return m.group(2).strip() or m.group(1), True
    return None, False


def _perk_status(lines: list[str], site: str) -> str:
    for line in lines:
        head = line.strip().rstrip("。.").split(" ", 1)[0]
        if site == "cn":
            if head in _ADDED:
                return "added"
            if head in _REMOVED:
                return "removed"
            if any(k in line for k in ("改为了", "改为")):
                return "moved"
        else:
            if head in _ADDED:
                return "added"
            if head in _REMOVED:
                return "removed"
            if "Reworked" in line:
                return "reworked"
            if "Moved" in line:
                return "moved"
    return "changed"


def reclassify_patch_dict(data: dict) -> int:
    """Move perk-shaped ability entries into perks; returns number moved."""
    moved = 0
    for section in data.get("sections", []):
        for hero in section.get("heroes", []):
            abilities = hero.get("abilities", [])
            perks = list(hero.get("perks", []))
            kept = []
            for ab in abilities:
                en_name = ab.get("name_en")
                cn_name = ab.get("name_cn")
                stripped_en, is_en_perk = _perk_shape(en_name or "")
                stripped_cn, is_cn_perk = _perk_shape(cn_name or "")
                if not (is_en_perk or is_cn_perk):
                    kept.append(ab)
                    continue
                changes = ab.get("changes", [])
                lines_en = [c["text_en"] for c in changes if c.get("text_en")]
                lines_cn = [c["text_cn"] for c in changes if c.get("text_cn")]
                site = "en" if en_name else "cn"
                perks.append({
                    "name_en": stripped_en if en_name else None,
                    "name_cn": stripped_cn if cn_name else None,
                    "status": _perk_status(lines_en if site == "en" else lines_cn, site),
                    "lines_en": lines_en,
                    "lines_cn": lines_cn,
                })
                moved += 1
            hero["abilities"] = kept
            hero["perks"] = perks
    return moved


def split_merged_perk_general(data: dict) -> int:
    """Split '名——主要威能 描述…' general lines into perk entries; returns count."""
    moved = 0
    for section in data.get("sections", []):
        for hero in section.get("heroes", []):
            general = hero.get("general", [])
            perks = list(hero.get("perks", []))
            kept = []
            for line in general:
                text = line if isinstance(line, str) else (
                    line.get("text_en") or line.get("text_cn") or "")
                m = _CN_MERGED_RE.match(text.strip())
                if m:
                    name, tier, body = m.group(1).strip(), m.group(2), m.group(3).strip()
                    # a body may itself hold the status marker ('已添加 …' / '已移除')
                    perks.append({
                        "name_en": None, "name_cn": name,
                        "status": _perk_status([body], "cn"),
                        "lines_en": [], "lines_cn": [body],
                    })
                    moved += 1
                else:
                    kept.append(line)
            hero["general"] = kept
            hero["perks"] = perks
    return moved
