"""Full offline data regeneration (reclassify, re-enrich, pair, map, heroes).

Usage:
  python tools/rebuild.py --data data

Delegates to pipeline.regenerate_all; manifest hashes are untouched (they are
computed pre-enrichment). Safe to run anytime; produces no monitor events.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from ow2_patch.pipeline import regenerate_all

DEFAULT_DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate all derived patch data")
    parser.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA)
    args = parser.parse_args(argv)

    regenerate_all(args.data)
    print("regeneration complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
