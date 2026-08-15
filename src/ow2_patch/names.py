"""Hero/ability name resolution: EN<->CN mapping table lookup + slug generation.

Unknown names are never fatal: they get a deterministic auto-slug and are recorded
in an `unknown` list so a human can add them to data/names.json later.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import unicodedata

DEFAULT_NAMES_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "names.json"

# Known variant spellings / retired names -> canonical EN name used as table key.
HERO_ALIASES = {
    "Solider: 76": "Soldier: 76",  # Blizzard typos on old pages
    "Soldier:76": "Soldier: 76",
    "Junkerqueen": "Junker Queen",
    "Iliari": "Illari",
    "McCree": "Cassidy",  # renamed in 2022; OW1-era patches used McCree
}
ABILITY_ALIASES = {}


def slugify(text: str) -> str:
    """Normalize to lowercase ascii slug (Soldier: 76 -> soldier-76, D.Va -> d-va).

    Never returns an empty string: pure-CJK or all-punctuation input falls back to a
    deterministic hash-based slug so timeline entries can never collapse onto ''.
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not slug:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
        slug = f"hero-{digest}"
    return slug


def _normalize_key(text: str) -> str:
    """Case- and accent-insensitive key for table lookups (Lúcio -> lucio)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return text.strip()


def _strip_parenthetical(name: str) -> str:
    """'Vendetta (New)' -> 'Vendetta'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def _normalize_cn(text: str) -> str:
    """CN names vary in punctuation ('士兵：76' vs '士兵76'); strip full-width noise."""
    text = text.strip().strip('"“”')
    return re.sub(r"[：:\s·、（）()「」『』'\"‘’“”]", "", text)


class NameResolver:
    def __init__(self, path: pathlib.Path = DEFAULT_NAMES_PATH):
        with open(path, encoding="utf-8") as fh:
            table = json.load(fh)
        self.heroes: dict[str, dict] = table["heroes"]
        self.abilities: dict[str, dict] = table["abilities"]
        self._hero_key = {_normalize_key(k): k for k in self.heroes}
        self._hero_cn_to_en = {_normalize_cn(v["cn"]): k for k, v in self.heroes.items()}
        self._ability_key = {_normalize_key(k): k for k in self.abilities}
        self._ability_cn_to_en = {_normalize_cn(v["cn"]): k for k, v in self.abilities.items()}
        self.unknown_heroes: list[tuple[str, str]] = []  # (name, site)
        self.unknown_abilities: list[tuple[str, str]] = []

    def hero(self, name: str, site: str) -> tuple[str, str | None, str | None, str | None]:
        """Resolve a hero display name -> (slug, name_en, name_cn, role)."""
        entry = self._lookup(self.heroes, self._hero_key, self._hero_cn_to_en,
                             HERO_ALIASES, name, site)
        if entry is None:
            self.unknown_heroes.append((name, site))
            if site == "en":
                return slugify(name), name, None, None
            return slugify(name), None, name, None
        return entry["slug"], entry.get("name_en"), entry.get("name_cn"), entry.get("role")

    def ability(self, name: str, site: str) -> tuple[str, str | None, str | None]:
        """Resolve an ability display name -> (slug, name_en, name_cn)."""
        entry = self._lookup(self.abilities, self._ability_key, self._ability_cn_to_en,
                             ABILITY_ALIASES, name, site)
        if entry is None:
            self.unknown_abilities.append((name, site))
            if site == "en":
                return slugify(name), name, None
            return slugify(name), None, name
        return entry["slug"], entry.get("name_en"), entry.get("name_cn")

    def _lookup(self, table: dict, key_index: dict, cn_to_en: dict, aliases: dict,
                name: str, site: str) -> dict | None:
        stripped = name.strip().strip('"“”')
        if site == "en":
            stripped = _strip_parenthetical(stripped)
            canonical = aliases.get(stripped, stripped)
            real_key = key_index.get(_normalize_key(canonical))
            if real_key is None:
                return None
            entry = table[real_key]
            return {"name_en": canonical, "name_cn": entry["cn"], "slug": entry["slug"],
                    "role": entry.get("role")}
        en = cn_to_en.get(_normalize_cn(stripped))
        if en is None:
            return None
        entry = table[en]
        return {"name_en": en, "name_cn": stripped, "slug": entry["slug"],
                "role": entry.get("role")}
