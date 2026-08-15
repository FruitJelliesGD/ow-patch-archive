"""Ability/perk map derivation tests (real-data assertions + variant folding)."""

from __future__ import annotations

import json
import pathlib

from ow2_patch.ability_map import build_ability_map
from ow2_patch.pairing import pair_patches, patch_meta_from_manifest

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def _build():
    en, cn = patch_meta_from_manifest(DATA)
    result = pair_patches(en, cn)
    return build_ability_map(DATA, result.pairs)


def test_heavy_pulse_rifle_cn_resolves():
    m = _build()
    assert m["by_cn"]["重脉冲步枪"] == ["heavy-pulse-rifle"]
    assert m["abilities"]["heavy-pulse-rifle"]["name_en"] == "Heavy Pulse Rifle"


def test_stim_pack_cn_resolves():
    m = _build()
    assert m["by_cn"]["强化药剂"] == ["stim-pack"]


def test_helix_singular_plural_merge():
    m = _build()
    entry = m["abilities"]["helix-rockets"]
    assert "Helix Rockets" in entry["en_variants"]
    # rebuild canonicalizes the singular spelling into the plural entry
    assert m["by_en"]["Helix Rockets"] == "helix-rockets"
    assert entry["name_en"] == "Helix Rockets"


def test_map_deterministic():
    assert _build() == _build()


def test_perk_map_present():
    m = _build()
    assert m["perks"], "expected a non-empty perk map"
    for slug, entry in list(m["perks"].items())[:20]:
        assert entry["en_variants"]
