"""Re-enrich stored patch JSONs after data/names.json edits and rebuild hero files.

Usage:
  python tools/rebuild.py --data data

Rewrites every data/patches/*/*.json with fresh name resolution (slugs, cross-language
names) without touching the manifest hashes (which are computed pre-enrichment), then
rebuilds heroes/*.json and heroes_index.json. Safe to run anytime; produces no events.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from ow2_patch.names import NameResolver
from ow2_patch.pipeline import build_hero_files

DEFAULT_DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def reenrich_patch_dict(data: dict, resolver: NameResolver) -> None:
    for section in data.get("sections", []):
        for hero in section.get("heroes", []):
            if hero.get("name_en"):
                slug, en, cn, role = resolver.hero(hero["name_en"], "en")
            elif hero.get("name_cn"):
                slug, en, cn, role = resolver.hero(hero["name_cn"], "cn")
            else:
                continue
            hero["slug"] = slug
            hero["name_en"] = en or hero.get("name_en")
            hero["name_cn"] = cn or hero.get("name_cn")
            if not hero.get("role"):
                hero["role"] = role
            for ability in hero.get("abilities", []):
                if ability.get("name_en"):
                    aslug, aen, acn = resolver.ability(ability["name_en"], "en")
                elif ability.get("name_cn"):
                    aslug, aen, acn = resolver.ability(ability["name_cn"], "cn")
                else:
                    continue
                ability["slug"] = aslug
                ability["name_en"] = aen or ability.get("name_en")
                ability["name_cn"] = acn or ability.get("name_cn")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-enrich stored patch data")
    parser.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA)
    args = parser.parse_args(argv)

    resolver = NameResolver(args.data / "names.json")
    count = 0
    for site_dir in ("en", "cn"):
        for patch_file in sorted((args.data / "patches" / site_dir).glob("*.json")):
            data = json.loads(patch_file.read_text(encoding="utf-8"))
            reenrich_patch_dict(data, resolver)
            patch_file.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            count += 1
    print(f"re-enriched {count} patch files")

    for name, site in resolver.unknown_heroes:
        print(f"WARN: unknown hero {name!r} ({site})")
    for name, site in resolver.unknown_abilities:
        print(f"WARN: unknown ability {name!r} ({site})")

    build_hero_files(args.data, resolver)
    print("hero files rebuilt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
