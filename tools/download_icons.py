"""Download patch-note icons (hero portraits + ability icons) into web assets.

Scans every archived patch JSON for captured official icon URLs and saves one
file per hero/ability slug under web/assets/icons/. Idempotent and incremental:
existing files are skipped, so re-running after a data update only fetches icons
that are new. Network failures are warnings, never a non-zero exit — a transient
CDN hiccup must not fail the monitor commit step.

Naming: heroes/<slug>.png and abilities/<hero-slug>/<ability-slug>.png. Ability
slugs are NOT hero-unique (e.g. quick-melee belongs to several heroes), hence
the hero-prefixed directory.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.parse
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DATA = REPO_ROOT / "data"
DEFAULT_OUT = REPO_ROOT / "web" / "assets" / "icons"

_UA = {"User-Agent": "ow2-patch-archive/0.1"}


def collect_icon_refs(data_dir: pathlib.Path) -> dict[tuple[str, str], tuple[str, str]]:
    """(kind, key) -> (url, date); prefers netease (cn) over cloudfront (en).

    key is the hero slug for kind "hero" and "hero-slug/ability-slug" for
    "ability". Among equal-preference URLs the latest patch date wins.
    """
    refs: dict[tuple[str, str], tuple[str, str]] = {}

    def prefer(key, url: str, date: str) -> None:
        def score(cand: tuple[str, str]) -> tuple[int, str]:
            host = urllib.parse.urlparse(cand[0]).netloc
            return (1 if "netease" in host else 0, cand[1])
        cand = (url, date)
        if key not in refs or score(cand) > score(refs[key]):
            refs[key] = cand

    for site in ("en", "cn"):
        for patch_file in sorted((data_dir / "patches" / site).glob("*.json")):
            data = json.loads(patch_file.read_text(encoding="utf-8"))
            date = data.get("date", "")
            for section in data.get("sections", []):
                for hero in section.get("heroes", []):
                    hero_slug = hero.get("slug")
                    if hero.get("icon") and hero_slug:
                        prefer(("hero", hero_slug), hero["icon"], date)
                    for ability in hero.get("abilities", []):
                        if ability.get("icon") and ability.get("slug") and hero_slug:
                            key = ("ability", f"{hero_slug}/{ability['slug']}")
                            prefer(key, ability["icon"], date)
    return refs


def _fetch(url: str) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"non-https icon URL: {url}")
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _is_image(data: bytes) -> bool:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if data.startswith(b"\xff\xd8\xff"):
        return True
    return data.startswith(b"RIFF") and data[8:12] == b"WEBP"


def _ext_for(url: str) -> str:
    # canonical .png matches the web page's hardcoded icon paths; browsers
    # sniff the actual image format regardless of the file extension
    return ".png"


def download_icons(
    data_dir: pathlib.Path,
    out_dir: pathlib.Path,
    dry_run: bool = False,
    marker: pathlib.Path | None = None,
) -> int:
    """Fetch missing icons; returns the number of newly downloaded files."""
    refs = collect_icon_refs(data_dir)
    subdir = {"hero": "heroes", "ability": "abilities"}
    new: list[str] = []
    for (kind, key), (url, date) in sorted(refs.items()):
        rel = pathlib.PurePosixPath(subdir[kind]) / f"{key}{_ext_for(url)}"
        dest = out_dir / rel
        if dest.exists():
            continue
        if dry_run:
            print(f"would download {rel} <- {url}")
            new.append(str(rel))
            continue
        try:
            data = _fetch(url)
        except Exception as exc:
            print(f"WARN: failed to download {url}: {exc}")
            continue
        if not _is_image(data):
            print(f"WARN: {url} did not return an image; skipping")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        new.append(str(rel))
        print(f"downloaded {rel}")
    if marker and new:
        marker.write_text(json.dumps({"icons": len(new)}), encoding="utf-8")
    print(f"icons: {len(refs)} unique, {len(new)} new"
          + (" (dry run)" if dry_run else ""))
    return len(new)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA,
                        help="data directory containing patches/ (default: repo data/)")
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT,
                        help="icon output directory (default: web/assets/icons)")
    parser.add_argument("--dry-run", action="store_true",
                        help="only report which icons would be downloaded")
    parser.add_argument("--marker", type=pathlib.Path, default=None,
                        help="write a marker JSON here when new icons were downloaded")
    args = parser.parse_args(argv)
    download_icons(args.data, args.out, dry_run=args.dry_run, marker=args.marker)
    return 0


if __name__ == "__main__":
    sys.exit(main())
