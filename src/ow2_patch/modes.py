"""Patch mode classification: standard balance patches vs special-mode patches.

Special modes (community modes, April Fools, experiments, hero trials, PTR,
announcements) contain hero changes that must not pollute the standard balance
history. Classification is regex-based: the patch title first, then the parsed
section headings (official "Community Crafted" / "社区创造模式" markers) —
a patch whose title reads standard but carries a community-created section
(e.g. p-2026-06-30-1) is still special.

The authoritative mode for a record is pair-level: build_patches_index stores
"either side non-standard wins", and build_hero_files looks records up through
that index — the CN April Fools title (完全正常…) is only reachable via its EN
pair's mode.
"""

from __future__ import annotations

import re

STANDARD = "standard"

# (mode, regex) in priority order
_MODE_RULES: list[tuple[str, re.Pattern]] = [
    ("quick_play_hacked", re.compile(r"Quick Play:?\s+Hacked", re.I)),
    ("april_fools", re.compile(r"Really, Really, Really Balanced|Totally Normal|完全正常", re.I)),
    ("experiment_6v6", re.compile(r"6v6 Experiment", re.I)),
    ("hero_trial", re.compile(r"Hero Trial|英雄试玩", re.I)),
    ("ptr", re.compile(r"\bPTR\b", re.I)),
    ("announcement", re.compile(r"Unauthorized Peripheral|Welcome to Overwatch", re.I)),
]

# official section marker for community-created-mode balance content (the patch
# title itself reads like a standard patch, e.g. p-2026-06-30-1)
_COMMUNITY_CREATED_SECTION_RE = re.compile(r"Community Crafted|社区创造模式", re.I)

# official April Fools section marker: the 2026-04-01 patch title reads like a
# standard patch but its first section is the Underwatch parody ("Underwatch
# Patch Notes" / "守望后卫补丁说明")
_APRIL_FOOLS_SECTION_RE = re.compile(r"Underwatch|守望后卫", re.I)

MODE_LABELS = {
    STANDARD: "常规",
    "quick_play_hacked": "快速比赛：黑客入侵",
    "april_fools": "愚人节",
    "experiment_6v6": "实验模式",
    "hero_trial": "英雄试玩",
    "ptr": "PTR 测试服",
    "announcement": "公告",
    "community_created": "社区创造模式",
}

# mirrored in web/app.js MODE_LABEL


def patch_mode(title: str) -> str:
    """Classify a patch title into a mode; unmatched titles are standard."""
    if not title:
        return STANDARD
    for mode, rx in _MODE_RULES:
        if rx.search(title):
            return mode
    return STANDARD


def patch_mode_with_sections(title: str, section_titles: list[str]) -> str:
    """Title rules first; a standard-looking title with an official section
    marker is classified special: Community Crafted / 社区创造模式 →
    community_created, the Underwatch parody (愚人节) → april_fools."""
    mode = patch_mode(title)
    if mode != STANDARD:
        return mode
    if any(_COMMUNITY_CREATED_SECTION_RE.search(t or "") for t in section_titles):
        return "community_created"
    if any(_APRIL_FOOLS_SECTION_RE.search(t or "") for t in section_titles):
        return "april_fools"
    return STANDARD
