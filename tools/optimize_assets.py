"""Shrink the static site's image assets to their real display size.

Two very different trees, hence two codecs:

``web/assets/icons/heroes/*.png``
    Real PNGs captured at 256x256 (~127 KB each) but displayed at 22-36 CSS px.
    Rewritten as <= 96x96 palette PNGs (~6 KB each, 12.5 MB -> 0.5 MB).

``web/assets/maps/**/*.png``
    Despite the ``.png`` name these are **JPEG** bytes (see ``_ext_for`` in
    ``tools/download_icons.py``: the paths are hardcoded, browsers sniff the
    real format). They are 2560x1440 / ~250-700 KB each but displayed at about
    570 CSS px. Rewritten as 1024px-wide progressive JPEG, keeping the same file
    name and extension so ``web/app.js`` needs no change.

``web/assets/icons/abilities/**`` is left untouched (already ~8 KB each).

Idempotent: a file already inside its byte budget is skipped, so running the
script twice leaves the tree byte-identical. ``tools/download_icons.py`` only
writes missing files, so optimized assets are never re-downloaded.

Run once, offline, then commit the assets:

    pip install -e ".[assets]"
    python tools/optimize_assets.py
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from PIL import Image

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_WEB = REPO_ROOT / "web"

HERO_MAX_SIDE = 96
HERO_COLORS = 128
HERO_BUDGET = 12 * 1024
MAP_MAX_WIDTH = 1024
MAP_QUALITY = 72
MAP_BUDGET = 140 * 1024


def _resize_to_fit(im: Image.Image, *, max_side: int | None, max_width: int | None) -> Image.Image:
    width, height = im.size
    if max_width and width > max_width:
        return im.resize((max_width, round(height * max_width / width)), Image.LANCZOS)
    if max_side and max(width, height) > max_side:
        scale = max_side / max(width, height)
        return im.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)
    return im


def _optimize_hero(path: pathlib.Path) -> int:
    """Palette PNG, alpha preserved."""
    with Image.open(path) as im:
        im.load()
        im = _resize_to_fit(im, max_side=HERO_MAX_SIDE, max_width=None)
        has_alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info
        if has_alpha:
            im = im.convert("RGBA").quantize(colors=HERO_COLORS, method=Image.Quantize.FASTOCTREE)
        else:
            im = im.convert("RGB").quantize(colors=HERO_COLORS, method=Image.Quantize.MEDIANCUT)
        im.save(path, "PNG", optimize=True)
    return path.stat().st_size


def _optimize_map(path: pathlib.Path) -> int:
    """Progressive JPEG written under the existing .png name (repo convention)."""
    with Image.open(path) as im:
        im.load()
        im = _resize_to_fit(im, max_side=None, max_width=MAP_MAX_WIDTH).convert("RGB")
        im.save(path, "JPEG", quality=MAP_QUALITY, optimize=True, progressive=True)
    return path.stat().st_size


def _group(name: str, files: list[pathlib.Path], *, budget: int, fn, dry_run: bool):
    before_total = after_total = changed = 0
    for path in files:
        before = path.stat().st_size
        after = before
        if not dry_run and before > budget:
            after = fn(path)
            changed += 1
        before_total += before
        after_total += after
    print(f"{name}: {len(files)} files, {before_total / 1e6:.1f} MB -> "
          f"{after_total / 1e6:.1f} MB ({changed} rewritten)")
    return before_total, after_total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--web", type=pathlib.Path, default=DEFAULT_WEB,
                        help="site root (default: repo web/)")
    parser.add_argument("--dry-run", action="store_true",
                        help="only report what would change")
    args = parser.parse_args(argv)

    icons = args.web / "assets" / "icons"
    maps = args.web / "assets" / "maps"
    hero_files = sorted((icons / "heroes").glob("*.png"))
    map_files = sorted(maps.rglob("*.png")) if maps.is_dir() else []
    ability_files = sorted((icons / "abilities").rglob("*.png"))

    if not hero_files and not map_files:
        print(f"no hero/map images under {args.web}", file=sys.stderr)
        return 1

    _group("hero icons", hero_files, budget=HERO_BUDGET, fn=_optimize_hero, dry_run=args.dry_run)
    _group("map screenshots", map_files, budget=MAP_BUDGET, fn=_optimize_map, dry_run=args.dry_run)
    ability_max = max((p.stat().st_size for p in ability_files), default=0)
    print(f"ability icons: {len(ability_files)} files, untouched (largest {ability_max / 1024:.0f} KB)")

    if args.dry_run:
        return 0
    oversized = [(p, p.stat().st_size) for p in hero_files if p.stat().st_size > HERO_BUDGET]
    oversized += [(p, p.stat().st_size) for p in map_files if p.stat().st_size > MAP_BUDGET]
    if oversized:
        for path, size in oversized[:10]:
            print(f"STILL OVER BUDGET: {path.relative_to(args.web)} {size / 1024:.0f} KB",
                  file=sys.stderr)
        if len(oversized) > 10:
            print(f"... and {len(oversized) - 10} more", file=sys.stderr)
        return 1
    print("all assets within budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
