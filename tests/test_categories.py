"""Content category phrase tests (src/ow2_patch/categories.py)."""

from __future__ import annotations

import pytest

from ow2_patch.categories import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    CATEGORY_RULES,
    categorize_content,
)
from ow2_patch.modes import MODE_LABELS

_MODE_KEYS = ("quick_play_hacked", "april_fools", "experiment_6v6", "hero_trial",
              "ptr", "community_created")


@pytest.mark.parametrize("text,expected", [
    # mode categories — EN + CN positives
    ("Quick Play Hacked: Assault Returns!", ["quick_play_hacked"]),
    ("在即将登场的快速比赛：黑客入侵中", ["quick_play_hacked"]),
    ("Totally Normal Patch Notes", ["april_fools"]),
    ("Underwatch Patch Notes", ["april_fools"]),
    ("守望后卫补丁说明", ["april_fools"]),
    ("6v6 Experiment is back", ["experiment_6v6"]),
    ("6v6 实验模式", ["experiment_6v6"]),
    ("Freja Hero Trial", ["hero_trial"]),
    ("英雄试玩：弗蕾娅", ["hero_trial"]),
    ("PTR Patch Notes", ["ptr"]),
    ("Community Crafted", ["community_created"]),
    ("社区创造模式", ["community_created"]),
    # content categories — EN + CN positives
    ("Summer Games", ["event"]),
    ("Winter Wonderland", ["event"]),
    ("冬境乐园", ["event"]),
    ("Season 18", ["season"]),
    ("第14赛季", ["season"]),
    ("New Hero: Freja", ["new_hero"]),
    ("New Heroes Added", ["new_hero"]),
    ("the new Support Hero Illari", ["new_hero"]),
    ("New Tank Hero", ["new_hero"]),
    ("新英雄无漾", ["new_hero"]),
    ("New map added", ["new_map"]),
    ("新地图", ["new_map"]),
    ("Stadium update", ["stadium"]),
    ("角斗领域", ["stadium"]),
    ("Arcade card", ["arcade"]),
    ("街机模式", ["arcade"]),
    ("Custom Games and Workshop", ["workshop"]),
    ("自定游戏", ["workshop"]),
    ("Overwatch League", ["owl"]),
    ("守望先锋联赛", ["owl"]),
    # multi-category, stable CATEGORY_ORDER
    ("Season 18 Stadium Quick Play", ["season", "stadium"]),
    # negatives — generic words must not hit curated phrases
    ("Game and Event Updates", []),
    ("New Hero Option: Beam Sensitivity", []),
    ("Quick Play, Competitive Play", []),
    ("April Fools' Day is over", []),
    ("A season of changes", []),
    ("a map vote", []),
    ("league of players", []),
    ("", []),
    (None, []),
])
def test_categorize_content(text: str | None, expected: list[str]):
    assert categorize_content(text) == expected


def test_category_tables_complete():
    assert len(CATEGORY_ORDER) == 14
    assert len(CATEGORY_RULES) == 14
    assert set(CATEGORY_ORDER) == set(CATEGORY_LABELS)
    assert [key for key, _en, _cn in CATEGORY_RULES] == CATEGORY_ORDER


def test_mode_category_labels_match_mode_labels():
    for key in _MODE_KEYS:
        assert CATEGORY_LABELS[key] == MODE_LABELS[key]
