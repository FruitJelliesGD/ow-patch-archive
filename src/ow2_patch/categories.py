"""Display-only content categories for the time browser.

Unlike modes (the classification authority that drives hero-history
filtering), categories are additive content tags: each patch's content is
scanned against a curated phrase table and the matching keys are stored on the
patches_index entry as `categories`. The frontend renders one badge per
category and offers a multi-select filter over them.

Every rule carries a scan SCOPE (CATEGORY_SCOPES): the whole content
(WHOLE — mode categories need this: standard-titled patches whose BODY
mentions the mode keep the badge without reclassification), title + section
titles + block titles (TITLE_SECTIONS), or title + first non-empty section
title (TITLE_FIRST — season launches). Body-level phrase hits are the dominant
false-positive source (bug-fix mentions, dev notes, reward boilerplate,
cosmetics), so content categories are title-scoped; per-key GUARDS handle the
remaining false positives (e.g. Stadium-roster "New Heroes Added" sections,
"Season N continues" first sections).

The category regexes overlap intentionally with the mode title rules in
modes.py: mode rules are title/section-scoped (authoritative), category rules
are display-only. The six mode categories reuse the mode phrase patterns and
their labels MUST stay identical to MODE_LABELS so a deduped badge never
changes text depending on its source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (key, EN regex, CN regex) in display/filter order
CATEGORY_RULES: list[tuple[str, str, str]] = [
    # mode categories — phrases mirror modes.py rules; labels mirror MODE_LABELS
    ("quick_play_hacked", r"Quick Play:?\s+Hacked", r"快速比赛：黑客入侵"),
    ("april_fools", r"Really, Really, Really Balanced|Totally Normal|Underwatch",
     r"完全正常|守望后卫"),
    ("experiment_6v6", r"6v6\s*Experiment", r"6v6\s*实验"),
    ("hero_trial", r"Hero Trial", r"英雄试玩"),
    ("ptr", r"\bPTR\b", r"PTR"),
    ("community_created", r"Community Crafted", r"社区创造模式"),
    # content categories
    ("event", r"Anniversary|Summer Games|Halloween|Winter Wonderland|Lunar New Year"
             r"|Archives|Starwatch|Junkenstein",
     r"周年庆|夏季运动会|万圣节|冬境乐园|春节|农历新年|行动档案|星际守望|狂鼠复仇"),
    ("season", r"Season\s+(?:\d+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)",
     r"第\d+赛季"),
    ("new_hero", r"New (?:Support |Tank |Damage )?Hero(?:s)?(?! Option)", r"新英雄"),
    ("new_map", r"New Maps?", r"新地图"),
    ("stadium", r"Stadium", r"角斗领域"),
    ("arcade", r"Arcade", r"街机"),
    ("workshop", r"Custom Game|Workshop", r"自定游戏|自定义游戏|工坊"),
    ("owl", r"(?-i:\bOWL\b)|Overwatch League", r"守望先锋联赛"),
    # brand collaborations (incl. Blizzard's own IPs); CN collab titles use
    # Latin brand scripts so EN phrases do the CN-side work, except 心之怪盗团
    ("crossover", r"collab|One[- ]?Punch Man|LE SSERAFIM|Cowboy Bebop|Transformers"
                  r"|Warcraft|My Hero Academia|Phantom Thieves|Street Fighter|Porsche",
     r"心之怪盗团"),
]

CATEGORY_ORDER: list[str] = [key for key, _en, _cn in CATEGORY_RULES]

# labels for the six mode keys MUST match modes.py MODE_LABELS exactly
CATEGORY_LABELS: dict[str, str] = {
    "quick_play_hacked": "快速比赛：黑客入侵",
    "april_fools": "愚人节",
    "experiment_6v6": "实验模式",
    "hero_trial": "英雄试玩",
    "ptr": "PTR 测试服",
    "community_created": "社区创造模式",
    "event": "活动",
    "season": "新赛季",
    "new_hero": "新英雄",
    "new_map": "新地图",
    "stadium": "角斗领域",
    "arcade": "街机",
    "workshop": "自定义工坊",
    "owl": "联赛",
    "crossover": "联动",
}

# mirrored in web/app.js CATEGORY_LABEL

# scan scopes — WHOLE: title + every content string (URLs skipped);
# TITLE_SECTIONS: title + section titles + block titles; TITLE_FIRST: title +
# first non-empty section title
WHOLE = "whole"
TITLE_SECTIONS = "title_sections"
TITLE_FIRST = "title_first"

CATEGORY_SCOPES: dict[str, str] = {
    # mode categories scan the whole content: standard-titled mixed patches
    # (e.g. p-2026-01-08-1's QP-Hacked block) keep the badge without
    # reclassification; stadium/workshop are body-driven too
    "quick_play_hacked": WHOLE,
    "april_fools": WHOLE,
    "experiment_6v6": WHOLE,
    "hero_trial": WHOLE,
    "ptr": WHOLE,
    "community_created": WHOLE,
    "event": TITLE_SECTIONS,
    "season": TITLE_FIRST,
    "new_hero": TITLE_SECTIONS,
    "new_map": TITLE_SECTIONS,
    "stadium": WHOLE,
    "arcade": TITLE_SECTIONS,
    "workshop": WHOLE,
    "owl": TITLE_SECTIONS,
    "crossover": TITLE_SECTIONS,
}

# a first-section "Season N continues" is a midseason patch, not a launch
_SEASON_CONTINUES = re.compile(r"continues|精彩继续", re.I)


@dataclass
class HeroContext:
    """Per-hero flags used by the new_hero Stadium guard."""
    stadium_items: bool  # non-empty stadium_items: Stadium-roster content
    has_changes: bool    # named ability with changes / perk / general text


@dataclass
class SectionContext:
    title: str
    block_titles: list[str]
    heroes: list[HeroContext]


@dataclass
class PatchContext:
    title: str
    first_section: str
    sections: list[SectionContext]
    all_strings: list[str]


_RULES: dict[str, re.Pattern] = {
    key: re.compile(f"{en}|{cn}", re.I) for key, en, cn in CATEGORY_RULES
}


def categorize_content(text: str) -> list[str]:
    """WHOLE-scope phrase match over a single text, in CATEGORY_ORDER order."""
    if not text:
        return []
    return [key for key in CATEGORY_ORDER if _RULES[key].search(text)]


def _stadium_or_stub_section(section: SectionContext) -> bool:
    """True when every hero of the section is Stadium-roster content (non-empty
    stadium_items) or a bare stub (no change content) — such sections (e.g. the
    Stadium roster 'New Heroes Added') must not badge new_hero. Sections with
    no hero blocks (pure announcements) are not guarded."""
    if not section.heroes:
        return False
    return all(h.stadium_items or not h.has_changes for h in section.heroes)


def _match_title_sections(key: str, ctx: PatchContext) -> bool:
    rx = _RULES[key]
    if rx.search(ctx.title or ""):
        return True
    for section in ctx.sections:
        if rx.search(section.title or ""):
            if not (key == "new_hero" and _stadium_or_stub_section(section)):
                return True
        # block titles are never guarded: a Stadium-guarded section can still
        # hold a real "New Hero: X" block
        if any(rx.search(t or "") for t in section.block_titles):
            return True
    return False


def _match_title_first(key: str, ctx: PatchContext) -> bool:
    rx = _RULES[key]
    for text in (ctx.title, ctx.first_section):
        if text and rx.search(text):
            if key == "season" and _SEASON_CONTINUES.search(text):
                continue  # midseason "Season N continues": not a launch
            return True
    return False


def categorize_patch(ctx: PatchContext) -> list[str]:
    """Category keys matching a patch's content under its per-rule scope, in
    CATEGORY_ORDER order."""
    found: set[str] = set()
    for key in CATEGORY_ORDER:
        scope = CATEGORY_SCOPES[key]
        if scope == WHOLE:
            if any(_RULES[key].search(t) for t in ctx.all_strings):
                found.add(key)
        elif scope == TITLE_SECTIONS:
            if _match_title_sections(key, ctx):
                found.add(key)
        elif scope == TITLE_FIRST:
            if _match_title_first(key, ctx):
                found.add(key)
    return [key for key in CATEGORY_ORDER if key in found]
