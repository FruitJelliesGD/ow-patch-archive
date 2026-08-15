"""CLI query tool for the archived patch data.

Usage:
  python tools/query.py soldier76              # slug / EN name / CN name
  python tools/query.py 士兵76
  python tools/query.py --site en --date 2026-08-15   # single patch raw content
  python tools/query.py soldier76 --json              # raw hero timeline JSON
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

DEFAULT_DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
SITE_LABEL = {"en": "英文", "cn": "中文"}
KIND_LABEL = {"ability": "技能", "perk": "威能", "general": "通用"}


def _norm(text: str) -> str:
    return re.sub(r"[\s：:·、（）()\-_'\"“”]", "", (text or "").lower())


def find_hero_slug(query: str, data_dir: pathlib.Path) -> str | None:
    q = _norm(query)
    for h in _index(data_dir):
        for field in (h["slug"], h["en"], h["cn"]):
            if field and _norm(field) == q:
                return h["slug"]
    return None


def _index(data_dir: pathlib.Path) -> list[dict]:
    return json.loads((data_dir / "heroes_index.json").read_text(encoding="utf-8"))["heroes"]


def query_hero(slug: str, data_dir: pathlib.Path) -> dict:
    return json.loads((data_dir / "heroes" / f"{slug}.json").read_text(encoding="utf-8"))


def print_hero_timeline(hero: dict) -> None:
    names = hero["names"]
    print(f"\n{names.get('cn') or ''} / {names.get('en') or ''} ({hero['role']}) — 共 {len(hero['timeline'])} 条记录\n")
    print(f"{'日期':<12} {'站':<4} {'类型':<4} {'技能/威能':<28} {'改动'}")
    print("-" * 120)
    for e in hero["timeline"]:
        name = e.get("ability_en") or e.get("ability_cn") or e.get("perk_en") or e.get("perk_cn") or "-"
        text = e.get("text_en") or e.get("text_cn") or " · ".join(
            (e.get("lines_en") or e.get("lines_cn") or [])[:2]
        )
        if e["kind"] == "perk":
            text = f"[{e.get('status')}] {text}"
        numbers = ""
        if e.get("before") is not None and e.get("after") is not None:
            numbers = f"  ({e['before']} → {e['after']})"
        print(f"{e['date']:<12} {SITE_LABEL[e['site']]:<4} {KIND_LABEL[e['kind']]:<4} {name[:28]:<28} {text[:60]}{numbers}")


def query_patch(site: str, date: str, data_dir: pathlib.Path) -> None:
    path = data_dir / "patches" / site / f"{date}-1.json"
    if not path.exists():
        print(f"no patch found for {site} {date}")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"\n{data['title']}\n{data['url']}\n")
    for section in data.get("sections", []):
        print(f"## {section.get('title')}")
        for hero in section.get("heroes", []):
            print(f"  {hero.get('name_en') or hero.get('name_cn')}")
            for ability in hero.get("abilities", []):
                print(f"    {ability.get('name_en') or ability.get('name_cn')}")
                for change in ability.get("changes", []):
                    print(f"      - {change.get('text_en') or change.get('text_cn')}")
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query archived Overwatch patch data")
    parser.add_argument("query", nargs="?", help="hero slug / EN name / CN name")
    parser.add_argument("--site", choices=["en", "cn"], help="patch lookup site")
    parser.add_argument("--date", help="patch lookup date YYYY-MM-DD")
    parser.add_argument("--json", action="store_true", help="dump raw hero JSON")
    parser.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA)
    args = parser.parse_args(argv)

    if args.site or args.date:
        if not (args.site and args.date):
            parser.error("--site and --date must be used together")
        query_patch(args.site, args.date, args.data)
        return 0
    if not args.query:
        parser.print_help()
        return 1

    slug = find_hero_slug(args.query, args.data)
    if slug is None:
        print(f"hero not found: {args.query}")
        return 1
    hero = query_hero(slug, args.data)
    if args.json:
        print(json.dumps(hero, ensure_ascii=False, indent=1))
    else:
        print_hero_timeline(hero)
    return 0


if __name__ == "__main__":
    sys.exit(main())
