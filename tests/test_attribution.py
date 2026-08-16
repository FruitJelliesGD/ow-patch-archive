"""Attribution tests: bracket prefixes, perk leaks, hero-attr classification."""

from __future__ import annotations

import json
import pathlib

from ow2_patch.attribution import classify_general
from ow2_patch.diff import patch_hash_from_dict
from ow2_patch.names import NameResolver

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
NAMES = DATA / "names.json"


def load_map():
    return json.loads((DATA / "ability_map.json").read_text(encoding="utf-8"))


def make_patch(site: str, hero_name: str, slug: str, general: list[str]) -> dict:
    return {
        "id": f"{site}-2026-08-12-1", "site": site, "date": "2026-08-12", "url": "https://x",
        "title": "T", "seq": 1,
        "sections": [{"type": "hero_update", "title": "Tank", "role": "tank",
                      "description": None, "heroes": [{
                          "slug": slug, "name_en": hero_name if site == "en" else None,
                          "name_cn": hero_name if site == "cn" else None,
                          "role": "tank", "dev_note": None,
                          "general": general, "perks": [], "abilities": []}],
                      "blocks": []}],
    }


def test_bracket_prefix_attaches_to_ability():
    resolver = NameResolver(NAMES)
    patch = make_patch("cn", "士兵76", "soldier-76",
                       ["[脉冲步枪]基础伤害从19点降低至18点。"])
    moved = classify_general(patch, resolver, load_map())
    assert moved == 1
    hero = patch["sections"][0]["heroes"][0]
    assert hero["general"] == []
    abilities = hero["abilities"]
    assert len(abilities) == 1
    assert abilities[0]["slug"] == "heavy-pulse-rifle"
    change = abilities[0]["changes"][0]
    assert change["text_cn"] == "[脉冲步枪]基础伤害从19点降低至18点。"
    assert change["before"] == 19.0 and change["after"] == 18.0


def test_bracket_unknown_name_stays_in_general():
    resolver = NameResolver(NAMES)
    patch = make_patch("en", "Doomfist", "doomfist", ["[Completely Unknown Ability] does things."])
    moved = classify_general(patch, resolver, load_map())
    assert moved == 0
    hero = patch["sections"][0]["heroes"][0]
    assert len(hero["general"]) == 1
    assert hero["abilities"] == []


def test_perk_name_leak_attaches():
    resolver = NameResolver(NAMES)
    patch = make_patch("en", "Ashe", "ashe", ["Head Honcho - Power", "B.O.B. Jr. - Power"])
    moved = classify_general(patch, resolver, load_map())
    assert moved == 2
    perks = patch["sections"][0]["heroes"][0]["perks"]
    assert {p["name_en"] for p in perks} == {"Head Honcho", "B.O.B. Jr."}
    assert all(p["status"] == "changed" for p in perks)


def test_hero_attr_classification():
    resolver = NameResolver(NAMES)
    patch = make_patch("en", "Bastion", "bastion", [
        "Ultimate cost reduced 7%.",
        "Base health reduced from 200 to 175.",
        "Something about maps.",
    ])
    moved = classify_general(patch, resolver, load_map())
    assert moved == 0  # none attributed away
    general = patch["sections"][0]["heroes"][0]["general"]
    subjects = {g["subject"]: g for g in general}
    assert subjects["ultimate_cost"]["by_pct"] == 7.0
    assert subjects["health"]["before"] == 200.0
    assert subjects["health"]["after"] == 175.0
    assert general[2]["dimension"] == "other"
    assert general[2]["subject"] is None


def test_attribution_does_not_change_hash():
    """The sorted text bag is stable across general -> abilities moves."""
    resolver = NameResolver(NAMES)
    before = make_patch("cn", "士兵76", "soldier-76", ["[脉冲步枪]基础伤害从19点降低至18点。"])
    hash_before = patch_hash_from_dict(before)
    classify_general(before, resolver, load_map())
    assert patch_hash_from_dict(before) == hash_before


def test_perk_attribution_keeps_original_text_and_hash():
    """A bare 'Name - Power' line must survive attribution with its original text."""
    resolver = NameResolver(NAMES)
    patch = make_patch("en", "Ashe", "ashe", ["Head Honcho - Power"])
    hash_before = patch_hash_from_dict(patch)
    classify_general(patch, resolver, load_map())
    hero = patch["sections"][0]["heroes"][0]
    assert hero["general"] == []
    perk = hero["perks"][0]
    assert perk["name_en"] == "Head Honcho"
    assert "Head Honcho - Power" in perk["raw_text"]
    # original text bag unchanged -> hash identical (no false 'modified' on re-parse)
    assert patch_hash_from_dict(patch) == hash_before
