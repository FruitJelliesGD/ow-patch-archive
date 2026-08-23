"""Display-only content categories for the time browser.

Unlike modes (the classification authority that drives hero-history
filtering), categories are additive content tags: each patch's whole content
(EN + CN sides) is scanned for curated phrases and the matching keys are
stored on the patches_index entry as `categories`. The frontend renders one
badge per category and offers a multi-select filter over them.

The category regexes overlap intentionally with the mode title rules in
modes.py: mode rules are title/section-scoped (authoritative), category rules
scan the whole content (display only). The six mode categories reuse the mode
phrase patterns and their labels MUST stay identical to MODE_LABELS so a
deduped badge never changes text depending on its source.
"""

from __future__ import annotations

import re

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
    ("season", r"Season\s+\d+", r"第\d+赛季|(?<!\d)\d+赛季"),
    ("new_hero", r"New Hero(?:s)?(?! Option)", r"新英雄"),
    ("new_map", r"New Maps?", r"新地图"),
    ("stadium", r"Stadium", r"角斗领域"),
    ("arcade", r"Arcade", r"街机"),
    ("workshop", r"Custom Game|Workshop", r"自定游戏|自定义游戏|工坊"),
    ("owl", r"\bOWL\b|Overwatch League", r"联赛|守望先锋联赛"),
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
}

# mirrored in web/app.js CATEGORY_LABEL

_RULES: list[tuple[str, re.Pattern]] = [
    (key, re.compile(f"{en}|{cn}", re.I)) for key, en, cn in CATEGORY_RULES
]


def categorize_content(text: str) -> list[str]:
    """Category keys whose phrase matches text, in CATEGORY_ORDER order."""
    if not text:
        return []
    return [key for key, rx in _RULES if rx.search(text)]
