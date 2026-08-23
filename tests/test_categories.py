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


# ---------- scoped scanning (categorize_patch) ----------

from ow2_patch.categories import (  # noqa: E402
    HeroContext,
    PatchContext,
    SectionContext,
    categorize_patch,
)


def _ctx(title="", first="", sections=None, strings=None) -> PatchContext:
    return PatchContext(
        title=title, first_section=first,
        sections=sections or [], all_strings=strings or [])


def _sec(title, heroes=(), block_titles=()) -> SectionContext:
    return SectionContext(title=title, block_titles=list(block_titles),
                          heroes=list(heroes))


def _hero(stadium=False, changes=True) -> HeroContext:
    return HeroContext(stadium_items=stadium, has_changes=changes)


def test_scopes_body_phrase_does_not_match_title_scoped_keys():
    """Body-level phrases (the dominant false-positive source: bug fixes, dev
    notes, reward boilerplate) must not tag TITLE_SECTIONS/TITLE_FIRST keys."""
    ctx = _ctx(title="Retail Patch Notes", strings=[
        "Season 18 bug fixes", "New Hero balance changes", "Arcade reward",
        "Summer Games skin", "Overwatch League shop bug", "New map in dev notes"])
    assert categorize_patch(ctx) == []


def test_title_sections_scope_matches_section_and_block_titles():
    ctx = _ctx(title="Patch Notes", first="Season 18", sections=[
        _sec("Season 18"), _sec("General", block_titles=["New Hero: Freja"])])
    keys = categorize_patch(ctx)
    assert "season" in keys and "new_hero" in keys
    assert "event" not in keys


def test_title_first_scope_ignores_deep_sections():
    """season is TITLE_FIRST: a deep-section 'Season N' (e.g. arcade-mode
    seasons, 'LIGHTING FOR SEASON 7') must not tag the patch."""
    ctx = _ctx(title="Patch Notes", first="General Updates",
               sections=[_sec("Season 18"), _sec("LIGHTING FOR SEASON 7")])
    assert "season" not in categorize_patch(ctx)


def test_season_first_section_match_and_continues_guard():
    assert "season" in categorize_patch(
        _ctx(title="Patch Notes", first="WELCOME TO SEASON 18"))
    # midseason 'Season N continues' is not a launch
    assert "season" not in categorize_patch(
        _ctx(title="Patch Notes", first="Season 18 continues"))
    assert "season" not in categorize_patch(
        _ctx(title="Patch Notes", first="第18赛季精彩继续"))


def test_season_spelled_out_numbers():
    assert "season" in categorize_patch(
        _ctx(title="Battle Pass starting with Season One", first=""))


def test_owl_case_sensitive_and_scoped():
    """\bOWL\b is case-sensitive (Snow Owl Ana must not match) and
    Overwatch League body mentions are excluded by the title scope."""
    assert "owl" in categorize_patch(_ctx(title="OWL Grand Finals", sections=[_sec("League")]))
    assert "owl" not in categorize_patch(_ctx(title="Snow Owl Ana skin", sections=[_sec("Skins")]))
    assert "owl" not in categorize_patch(_ctx(strings=["the Overwatch League shop"]))
    assert "owl" in categorize_patch(_ctx(sections=[_sec("Overwatch League season recap")]))


def test_new_hero_stadium_section_guard():
    """Section-title 'New Heroes Added' over Stadium-roster heroes (non-empty
    stadium_items) or bare stubs must not badge new_hero; real intro sections
    and block-title matches stay."""
    stadium = _sec("New Heroes Added", heroes=[_hero(stadium=True), _hero(stadium=True)])
    assert "new_hero" not in categorize_patch(_ctx(sections=[stadium]))
    stub = _sec("New Heroes Added", heroes=[_hero(changes=False)])
    assert "new_hero" not in categorize_patch(_ctx(sections=[stub]))
    real = _sec("New Hero: Freja", heroes=[_hero()])
    assert "new_hero" in categorize_patch(_ctx(sections=[real]))
    empty = _sec("New Hero: Mauga")  # announcement section without hero blocks
    assert "new_hero" in categorize_patch(_ctx(sections=[empty]))
    # block-title matches are not guarded: Baptiste's section is a bare stub
    baptiste = _sec("Hero Updates", heroes=[_hero(changes=False)],
                    block_titles=["New Hero: Baptiste"])
    assert "new_hero" in categorize_patch(_ctx(sections=[baptiste]))


def test_whole_scope_mode_categories_keep_body_signal():
    """quick_play_hacked stays WHOLE: a standard-titled patch whose BODY
    mentions the mode keeps the badge (p-2026-01-08-1 case)."""
    ctx = _ctx(title="Retail Patch Notes", strings=["Quick Play: Hacked: Assault Returns!"])
    assert "quick_play_hacked" in categorize_patch(ctx)
