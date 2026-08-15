"""Extract frozen HTML fixtures from live pages for the parser tests."""
import pathlib
import sys

from ow2_patch.fetch import Fetcher
from ow2_patch.parse import _PATCH_SPLIT_RE

FIXTURES = pathlib.Path("tests/fixtures")


def extract_patches(html: str, count: int) -> str:
    parts = _PATCH_SPLIT_RE.split(html)
    chunks = [p for p in parts if "PatchNotes-patch" in p]
    return "\n".join(chunks[:count])


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    f = Fetcher()

    en = f.fetch_month("en", 2026, 8).html
    (FIXTURES / "en_2026_08.html").write_text(extract_patches(en, 2), encoding="utf-8")
    print("en_2026_08:", extract_patches(en, 2)[:60], "...")

    cn = f.fetch_month("cn", 2026, 8).html
    (FIXTURES / "cn_2026_08.html").write_text(extract_patches(cn, 2), encoding="utf-8")
    print("cn_2026_08 ok")

    legacy = f.fetch_month("en", 2016, 5).html
    (FIXTURES / "en_2016_05.html").write_text(extract_patches(legacy, 1), encoding="utf-8")
    print("en_2016_05 ok")

    # same-day multi: duplicate the first 2026-08 patch
    first = extract_patches(en, 1)
    (FIXTURES / "en_same_day_multi.html").write_text(first + "\n" + first, encoding="utf-8")
    print("en_same_day_multi ok")


if __name__ == "__main__":
    sys.exit(main())
