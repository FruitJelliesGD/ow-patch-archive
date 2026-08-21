"""Patch mode classification tests (src/ow2_patch/modes.py)."""

from __future__ import annotations

import pytest

from ow2_patch.modes import MODE_LABELS, patch_mode


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
                        ("announcement", "公告")]:
        assert MODE_LABELS[mode] == title
