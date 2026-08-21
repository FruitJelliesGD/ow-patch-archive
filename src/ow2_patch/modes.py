"""Patch mode classification: standard balance patches vs special-mode patches.

Special modes (community modes, April Fools, experiments, hero trials, PTR,
announcements) contain hero changes that must not pollute the standard balance
history. Classification is title-regex only (no manual list): a future
unknown-mode title defaults to "standard".

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

MODE_LABELS = {
    STANDARD: "常规",
    "quick_play_hacked": "社区模式",
    "april_fools": "愚人节",
    "experiment_6v6": "实验模式",
    "hero_trial": "英雄试玩",
    "ptr": "PTR 测试服",
    "announcement": "公告",
}

# mirrored in web/app.js MODE_LABEL
MODE_LABEL_EN = {
    STANDARD: "Standard",
    "quick_play_hacked": "Quick Play: Hacked",
    "april_fools": "April Fools",
    "experiment_6v6": "6v6 Experiment",
    "hero_trial": "Hero Trial",
    "ptr": "PTR",
    "announcement": "Announcement",
}


def patch_mode(title: str) -> str:
    """Classify a patch title into a mode; unmatched titles are standard."""
    if not title:
        return STANDARD
    for mode, rx in _MODE_RULES:
        if rx.search(title):
            return mode
    return STANDARD


def is_standard(mode: str | None) -> bool:
    return not mode or mode == STANDARD
