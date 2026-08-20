"""Scoped legacy re-migration: re-fetch only the OW1-era months (EN 2016-05 ..
2020-01) and force-rewrite them with the structured legacy parser.

The modern months (2020-02+) use an unchanged parse path, so they are left
untouched — only the 103 legacy patches and their derived data (hero files,
entries, ability map, pairing) are regenerated.

Usage:
  python tools/migrate_legacy.py --data data
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from ow2_patch.fetch import Fetcher
from ow2_patch.pipeline import run_pipeline

DEFAULT_DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def legacy_months() -> list[tuple[str, int, int]]:
    """EN months 2016-05 .. 2020-01 (the structured legacy era)."""
    months: list[tuple[str, int, int]] = []
    for year in range(2016, 2021):
        for month in range(1, 13):
            if (year, month) < (2016, 5) or (year, month) > (2020, 1):
                continue
            months.append(("en", year, month))
    return months


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-parse and re-persist OW1 legacy patches")
    parser.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA)
    args = parser.parse_args(argv)

    months = legacy_months()
    print(f"re-scanning {len(months)} legacy months (en 2016-05..2020-01)")
    result = run_pipeline(args.data, months=months, fetch=Fetcher(), force_rewrite=True)
    for name, site in result.unknown_heroes:
        print(f"WARN: unknown hero {name!r} ({site}) — add to data/names.json")
    for name, site in result.unknown_abilities:
        print(f"WARN: unknown ability {name!r} ({site}) — add to data/names.json")
    print(f"legacy migration done: {result.fetched_months} months fetched, "
          f"{len(result.fetch_errors)} fetch errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
