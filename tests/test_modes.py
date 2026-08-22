"""Patch mode classification tests (src/ow2_patch/modes.py)."""

from __future__ import annotations

import pytest

from ow2_patch.modes import MODE_LABELS, patch_mode, patch_mode_with_sections


@pytest.mark.parametrize("title,mode", [
    ("Overwatch Retail Patch Notes - August 11, 2026", "standard"),
    ("OVERWATCH PATCH NOTES - FEBRUARY 28, 2017", "standard"),  # uppercase variant is standard
    ("Overwatch 2 Quick Play: Hacked - January 12, 2024", "quick_play_hacked"),
    ("Overwatch 2: Quick Play Hacked - November 6, 2024", "quick_play_hacked"),
    ("Overwatch 2 Really, Really, Really Balanced Patch Notes - April 1, 2024", "april_fools"),
    ("Totally Normal Patch Notes for Totally Normalwatch - April 1, 2025", "april_fools"),
    ("《守望先锋》完全正常的“完全正常先锋”补丁说明——2025年4月1日", "april_fools"),
    ("Overwatch 2 6v6 Experiment - December 17, 2024", "experiment_6v6"),
    ("Overwatch 2 Freja Hero Trial - March 21, 2025", "hero_trial"),
    ("《守望先锋》英雄试玩：弗蕾娅——2025年3月22日", "hero_trial"),
    ("Overwatch PTR Patch Notes - March 29, 2018", "ptr"),
    ("Welcome to Overwatch 2!", "announcement"),
    ("Update on Unauthorized Peripheral Usage for Console Platforms", "announcement"),
    ("", "standard"),
])
def test_patch_mode(title: str, mode: str):
    assert patch_mode(title) == mode


def test_all_modes_have_labels():
    for mode, title in [("standard", "常规"), ("quick_play_hacked", "社区模式"),
                        ("april_fools", "愚人节"), ("experiment_6v6", "实验模式"),
                        ("hero_trial", "英雄试玩"), ("ptr", "PTR 测试服"),
                        ("announcement", "公告"),
                        ("community_created", "社区创造模式")]:
        assert MODE_LABELS[mode] == title


def test_patch_mode_with_sections_community_created():
    """A standard-looking title with an official Community Crafted section
    marker classifies as community_created (p-2026-06-30-1 shape)."""
    title = "Overwatch Retail Patch Notes - June 30, 2026"
    assert patch_mode(title) == "standard"
    assert patch_mode_with_sections(title, ["Game Client Update"]) == "standard"
    assert patch_mode_with_sections(title, ["Community Crafted"]) == "community_created"
    assert patch_mode_with_sections(title, ["社区创造模式"]) == "community_created"
    assert patch_mode_with_sections(title, ["社区创造模式", "Tank"]) == "community_created"
    # title rules win over the section signal
    assert patch_mode_with_sections("Overwatch 2 Really, Really, Really Balanced Patch Notes - April 1, 2024",
                                   ["Community Crafted"]) == "april_fools"


def test_patch_mode_with_sections_april_fools():
    """A standard-looking title with the official Underwatch parody section
    marker classifies as april_fools (en-2026-04-01-1 shape, 50 heroes)."""
    title = "Overwatch Retail Patch Notes - April 1, 2026"
    assert patch_mode(title) == "standard"
    assert patch_mode_with_sections(title, ["Tank", "Damage", "Support"]) == "standard"
    assert patch_mode_with_sections(title, ["Underwatch Patch Notes", "Tank"]) == "april_fools"
    assert patch_mode_with_sections(title, ["守望后卫补丁说明"]) == "april_fools"
    # title rules win over the section signal
    assert patch_mode_with_sections("Totally Normal Patch Notes for Totally Normalwatch - April 1, 2025",
                                   ["Underwatch Patch Notes"]) == "april_fools"
