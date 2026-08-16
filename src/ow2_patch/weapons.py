"""Weapon classification: curated seed table + name-root matching.

The seed table (data/weapons.json) is the authoritative human-maintained list;
name roots are a conservative fallback. Classification runs whenever the ability
map is rebuilt, so editing data/weapons.json + `tools/rebuild.py` re-labels.
"""

from __future__ import annotations

import json
import pathlib

DEFAULT_WEAPONS_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "weapons.json"


def load_weapons(path: pathlib.Path | None = None) -> dict:
    if path is None or not path.exists():
        path = DEFAULT_WEAPONS_PATH
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def classify_ability(name_en: str, name_cn: str, hero_slug: str, weapons: dict) -> str:
    """Return 'weapon' or 'ability' for an ability display name."""
    name = name_en or name_cn or ""
    if not name:
        return "ability"
    for entry in weapons.get("weapons", []):
        if entry.get("hero") == hero_slug and entry.get("name_en") == name_en:
            return "weapon"
        if entry.get("name_cn") and entry.get("name_cn") == name:
            return "weapon"
    lower = name.lower()
    for root in weapons.get("roots", []):
        if root in lower:
            return "weapon"
    return "ability"
