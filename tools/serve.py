"""Stage the site (web/ + data/) into _site/ and serve locally for preview.

Usage:
  python tools/serve.py [--port 8000] [--no-serve]

With --no-serve it only builds _site/ (same layout the pages workflow deploys).
"""

from __future__ import annotations

import argparse
import http.server
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and serve the static query site")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-serve", action="store_true")
    args = parser.parse_args(argv)

    site = ROOT / "_site"
    if site.exists():
        shutil.rmtree(site)
    site.mkdir()
    for item in (ROOT / "web").iterdir():
        dst = site / item.name
        shutil.copytree(item, dst) if item.is_dir() else shutil.copy2(item, dst)
    shutil.copytree(ROOT / "data", site / "data")
    print(f"staged {len(list(site.iterdir()))} top-level items into {site}")

    if args.no_serve:
        return 0
    os.chdir(site)
    handler = http.server.SimpleHTTPRequestHandler
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"serving at http://127.0.0.1:{args.port} (Ctrl+C to stop)")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    import os

    sys.exit(main())
