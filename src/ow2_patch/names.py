"""Hero/ability name resolution: EN<->CN mapping table lookup + slug generation.

Unknown names are never fatal: they get a deterministic auto-slug and are recorded
in an `unknown` list so a human can add them to data/names.json later.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import unicodedata


def _default_names_path() -> pathlib.Path:
    """Locate data/names.json: repo checkout, CWD, or OW2_NAMES_PATH override.

    Works both for editable installs (source tree) and for a plain `pip install .`
    in CI where the package is copied into site-packages.
    """
    candidates = [
        pathlib.Path(os.environ["OW2_NAMES_PATH"]) / "names.json"
        if os.environ.get("OW2_NAMES_PATH") else None,
        pathlib.Path.cwd() / "data" / "names.json",
        pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "names.json",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return candidate
    return pathlib.Path.cwd() / "data" / "names.json"


DEFAULT_NAMES_PATH = _default_names_path()

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
    def __init__(self, path: pathlib.Path | None = None,
                 ability_map_path: pathlib.Path | None = None):
        if path is None or not path.exists():
            path = _default_names_path()
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

        # data-derived EN<->CN maps (see ability_map.py); optional, non-fatal if absent
        if ability_map_path is None:
            ability_map_path = path.parent / "ability_map.json"
        self.ability_map: dict = {}
        if ability_map_path.exists():
            with open(ability_map_path, encoding="utf-8") as fh:
                self.ability_map = json.load(fh)

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

    def is_known_hero(self, name: str, site: str) -> bool:
        """True only for names in the curated table (aliases included).

        Unlike hero(), unknown names must NOT auto-slug — the legacy parser
        uses this to tell hero blocks ("Ana") apart from plain category
        headings ("Heroes", "New Hero: Ana (Support)").
        """
        return self._lookup(self.heroes, self._hero_key, self._hero_cn_to_en,
                            HERO_ALIASES, name, site) is not None

    def ability(self, name: str, site: str,
                hero_slug: str | None = None) -> tuple[str, str | None, str | None]:
        """Resolve an ability display name -> (slug, name_en, name_cn).

        Priority: curated names.json -> data-derived ability_map -> auto slug.
        """
        entry = self._lookup(self.abilities, self._ability_key, self._ability_cn_to_en,
                             ABILITY_ALIASES, name, site)
        if entry is not None:
            return entry["slug"], entry.get("name_en"), entry.get("name_cn")
        return self._map_lookup("abilities", "by_cn", "by_en", name, site, hero_slug)

    def perk(self, name: str, site: str,
             hero_slug: str | None = None) -> tuple[str, str | None, str | None]:
        """Resolve a perk display name (威能) -> (slug, name_en, name_cn)."""
        entry = self._lookup(self.abilities, self._ability_key, self._ability_cn_to_en,
                             ABILITY_ALIASES, name, site)
        if entry is not None:
            return entry["slug"], entry.get("name_en"), entry.get("name_cn")
        return self._map_lookup("perks", "perks_by_cn", "perks_by_en", name, site, hero_slug)

    def _map_lookup(self, entries_key: str, by_cn_key: str, by_en_key: str,
                    name: str, site: str, hero_slug: str | None):
        """Consult the data-derived map; falls back to auto slug for unknown names."""
        stripped = name.strip().strip('"“”')
        if site == "en":
            slug = self.ability_map.get(by_en_key, {}).get(stripped)
        else:
            slugs = self.ability_map.get(by_cn_key, {}).get(stripped, [])
            slug = self._pick_slug(slugs, entries_key, hero_slug)
        if not slug:
            self.unknown_abilities.append((name, site))
            if site == "en":
                return slugify(name), name, None
            return slugify(name), None, name
        entry = self.ability_map.get(entries_key, {}).get(slug, {})
        return slug, entry.get("name_en"), entry.get("name_cn")

    def _pick_slug(self, slugs: list[str], entries_key: str, hero_slug: str | None) -> str | None:
        if not slugs:
            return None
        if hero_slug:
            entries = self.ability_map.get(entries_key, {})
            for slug in slugs:
                if hero_slug in entries.get(slug, {}).get("heroes", []):
                    return slug
        return slugs[0]

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
