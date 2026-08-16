"""Weapon classification tests."""

from __future__ import annotations

import pathlib

from ow2_patch.weapons import classify_ability, load_weapons

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
WEAPONS = load_weapons(DATA / "weapons.json")


def test_seed_table_exact_hit():
    assert classify_ability("Peacekeeper", "维和者", "cassidy", WEAPONS) == "weapon"
    assert classify_ability("Heavy Pulse Rifle", "重脉冲步枪", "soldier-76", WEAPONS) == "weapon"


def test_root_word_hit():
    assert classify_ability("Solar Rifle", None, "illari", WEAPONS) == "weapon"
    assert classify_ability("Hellfire Shotguns", None, "reaper", WEAPONS) == "weapon"


def test_non_weapon_ability_untouched():
    # ability names that share root words with weapons must stay abilities
    assert classify_ability("Rocket Punch", None, "doomfist", WEAPONS) == "ability"
    assert classify_ability("Recall", None, "tracer", WEAPONS) == "ability"
    assert classify_ability("Storm Arrow", None, "hanzo", WEAPONS) == "ability"


def test_seed_table_wins_over_roots():
    # a seed entry labels the weapon even when the name is unusual
    assert classify_ability("Thorn Volley", None, "lifeweaver", WEAPONS) == "weapon"


def test_empty_name_safe():
    assert classify_ability("", None, "ana", WEAPONS) == "ability"
