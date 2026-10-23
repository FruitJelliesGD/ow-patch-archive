"""CLI entry point for the AI translation backfill.

See ``src/ow2_patch/ai_translate.py`` for the implementation.
"""

from __future__ import annotations

import sys

from ow2_patch.ai_translate import main

if __name__ == "__main__":
    sys.exit(main())
