"""Pair EN/CN patches that describe the same logical update, then build a time index.

CN pages usually publish 1 day after EN, and Blizzard's anchor dates are occasionally
off (title date differs), so pairing maximizes the *number* of matches first
(maximum-cardinality minimum-weight bipartite matching) instead of greedily taking
the smallest date difference.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import date

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_EN_TITLE_DATE_RE = re.compile(r"([A-Z][a-z]{2,8})\s+(\d{1,2}),\s*(\d{4})")
_CN_TITLE_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def _parse_title_date(title: str, site: str) -> str | None:
    if site == "cn":
        m = _CN_TITLE_DATE_RE.search(title)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return None
    m = _EN_TITLE_DATE_RE.search(title)
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower()[:3])
    if not month:
        return None
    return f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"


def _day_diff(a: str, b: str) -> int:
    """Signed day difference a - b."""

    def parse(d: str) -> date:
        y, m, dd = (int(x) for x in d.split("-"))
        return date(y, m, dd)

    return (parse(a) - parse(b)).days


class MinCostMaxFlow:
    """Successive-shortest-path min-cost max-flow (SPFA); small graphs only."""

    def __init__(self, n: int):
        self.n = n
        self.graph: list[list[list]] = [[] for _ in range(n)]

    def add_edge(self, u: int, v: int, cap: int, cost: int) -> None:
        self.graph[u].append([v, cap, cost, len(self.graph[v])])
        self.graph[v].append([u, 0, -cost, len(self.graph[u]) - 1])

    def min_cost_max_flow(self, s: int, t: int) -> tuple[int, int]:
        flow = cost = 0
        while True:
            dist = [float("inf")] * self.n
            inq = [False] * self.n
            prevv = [0] * self.n
            preve = [0] * self.n
            dist[s] = 0
            dq = deque([s])
            inq[s] = True
            while dq:
                u = dq.popleft()
                inq[u] = False
                for i, e in enumerate(self.graph[u]):
                    if e[1] > 0 and dist[u] + e[2] < dist[e[0]]:
                        dist[e[0]] = dist[u] + e[2]
                        prevv[e[0]] = u
                        preve[e[0]] = i
                        if not inq[e[0]]:
                            dq.append(e[0])
                            inq[e[0]] = True
            if dist[t] == float("inf"):
                break
            d = float("inf")
            v = t
            while v != s:
                d = min(d, self.graph[prevv[v]][preve[v]][1])
                v = prevv[v]
            v = t
            while v != s:
                e = self.graph[prevv[v]][preve[v]]
                e[1] -= d
                self.graph[v][e[3]][1] += d
                v = prevv[v]
            flow += d
            cost += d * dist[t]
        return flow, cost


@dataclass
class PairResult:
    pairs: list[dict] = field(default_factory=list)
    unpaired_en: list[str] = field(default_factory=list)
    unpaired_cn: list[str] = field(default_factory=list)


def patch_meta_from_manifest(data_dir: pathlib.Path) -> tuple[list[dict], list[dict]]:
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    en, cn = [], []
    for patch_id, meta in manifest.items():
        if not isinstance(meta, dict) or patch_id == "hash_schema":
            continue
        seq = int(patch_id.split("-")[4])
        entry = {
            "patch_id": patch_id,
            "site": meta["site"],
            "date": meta["date"],
            "title": meta["title"],
            "url": meta["url"],
            "seq": seq,
            "title_date": _parse_title_date(meta["title"], meta["site"]),
        }
        (en if meta["site"] == "en" else cn).append(entry)
    en.sort(key=lambda p: (p["date"], p["seq"]))
    cn.sort(key=lambda p: (p["date"], p["seq"]))
    return en, cn


def pair_patches(en: list[dict], cn: list[dict]) -> PairResult:
    """Maximum-cardinality minimum-weight pairing of EN and CN patches.

    No pre-matching on exact dates: in a 1-day-lag cluster (EN 26..29 vs CN 27..30)
    exact-date pairs would consume the shared dates and strand the tail. The weighted
    matching maximizes the pair count first; the anchor-diff weight term already
    prefers same-date pairs whenever that does not cost a match.
    """
    result = PairResult()
    used_en: set[str] = set()
    used_cn: set[str] = set()

    src = 0
    cn_nodes = list(range(1, len(cn) + 1))
    en_nodes = list(range(len(cn) + 1, len(cn) + len(en) + 1))
    sink = len(cn) + len(en) + 1
    mcmf = MinCostMaxFlow(sink + 1)
    for i in cn_nodes:
        mcmf.add_edge(src, i, 1, 0)
    for j in en_nodes:
        mcmf.add_edge(j, sink, 1, 0)

    edges: dict[tuple[int, int], tuple[dict, dict]] = {}
    for i, q in enumerate(cn, start=1):
        for j, p in enumerate(en, start=1):
            exact = (p["date"], p["seq"]) == (q["date"], q["seq"])
            if not exact and (p["seq"] != 1 or q["seq"] != 1):
                continue
            anchor_diff = abs(_day_diff(p["date"], q["date"]))
            title_diff = 99
            if p["title_date"] and q["title_date"]:
                title_diff = abs(_day_diff(p["title_date"], q["title_date"]))
            if min(anchor_diff, title_diff) > 1:
                continue
            # lexicographic weight; en date breaks ties deterministically
            weight = (min(anchor_diff, title_diff) * 1000
                      + anchor_diff * 100
                      + min(title_diff, 99) * 10
                      + int(p["date"].replace("-", "")))
            mcmf.add_edge(cn_nodes[i - 1], en_nodes[j - 1], 1, weight)
            edges[(cn_nodes[i - 1], en_nodes[j - 1])] = (p, q)

    mcmf.min_cost_max_flow(src, sink)

    # read back saturated edges (capacity consumed -> flow of 1 sent)
    for (u, v), (p, q) in edges.items():
        entry = next(e for e in mcmf.graph[u] if e[0] == v)
        if entry[1] == 0:
            anchor_diff = abs(_day_diff(p["date"], q["date"]))
            title_diff = (abs(_day_diff(p["title_date"], q["title_date"]))
                          if p["title_date"] and q["title_date"] else None)
            by = "title" if (title_diff is not None and title_diff < anchor_diff) else "anchor"
            _pair(result, p, q, by=by, date_diff=anchor_diff, title_diff=title_diff)
            used_en.add(p["patch_id"])
            used_cn.add(q["patch_id"])

    result.unpaired_en = [p["patch_id"] for p in en if p["patch_id"] not in used_en]
    result.unpaired_cn = [q["patch_id"] for q in cn if q["patch_id"] not in used_cn]
    return result


def _pair(result: PairResult, en: dict, cn: dict, by: str,
          date_diff: int | None = None, title_diff: int | None = None) -> None:
    if date_diff is None:
        date_diff = abs(_day_diff(en["date"], cn["date"]))
    seq = len([p for p in result.pairs if p["date"] == en["date"]]) + 1
    result.pairs.append({
        "id": f"p-{en['date']}-{seq}",
        "date": en["date"],
        "en": {"patch_id": en["patch_id"], "date": en["date"], "seq": en["seq"],
               "title": en["title"], "url": en["url"]},
        "cn": {"patch_id": cn["patch_id"], "date": cn["date"], "seq": cn["seq"],
               "title": cn["title"], "url": cn["url"]},
        "match": {"date_diff": date_diff, "title_diff": title_diff, "by": by},
    })


def build_patches_index(data_dir: pathlib.Path, result: PairResult) -> None:
    """Write data/patches_index.json: logical patches sorted by date desc.

    Each entry carries a `mode` (see modes): pairs take either side non-standard
    ("either side non-standard wins", en first — the CN April Fools title is
    only reachable via its EN pair), then the official section markers
    (Community Crafted / 社区创造模式) catch standard-titled community-mode
    patches (p-2026-06-30-1); unpaired entries use their own title + sections.
    """
    from .modes import STANDARD, patch_mode_with_sections

    def _section_titles(patch_id: str) -> list[str]:
        site = patch_id.split("-", 1)[0]
        parts = patch_id.split("-")
        path = data_dir / "patches" / site / f"{'-'.join(parts[1:4])}-{parts[4]}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError:
            return []
        return [s.get("title") or "" for s in data.get("sections", [])]

    def _pair_mode(en: dict, cn: dict) -> str:
        en_mode = patch_mode_with_sections(en["title"], _section_titles(en["patch_id"]))
        if en_mode != STANDARD:
            return en_mode
        return patch_mode_with_sections(cn["title"], _section_titles(cn["patch_id"]))

    index: list[dict] = []
    for pair in result.pairs:
        mode = _pair_mode(pair["en"], pair["cn"])
        index.append({
            "id": pair["id"], "date": pair["date"],
            "title_en": pair["en"]["title"], "title_cn": pair["cn"]["title"],
            "url_en": pair["en"]["url"], "url_cn": pair["cn"]["url"],
            "sites": ["en", "cn"],
            "patch_id_en": pair["en"]["patch_id"], "patch_id_cn": pair["cn"]["patch_id"],
            "mode": mode,
        })
    for patch_id in result.unpaired_en + result.unpaired_cn:
        site = patch_id.split("-", 1)[0]
        parts = patch_id.split("-")
        date_str = "-".join(parts[1:4])
        seq = parts[4]
        meta = json.loads(
            (data_dir / "patches" / site / f"{date_str}-{seq}.json").read_text(encoding="utf-8")
        )
        index.append({
            "id": patch_id, "date": date_str,
            "title_en": meta["title"] if site == "en" else None,
            "title_cn": meta["title"] if site == "cn" else None,
            "url_en": meta["url"] if site == "en" else None,
            "url_cn": meta["url"] if site == "cn" else None,
            "sites": [site],
            "patch_id_en": patch_id if site == "en" else None,
            "patch_id_cn": patch_id if site == "cn" else None,
            "mode": patch_mode_with_sections(meta["title"], _section_titles(patch_id)),
        })

    index.sort(key=lambda e: (e["date"], e["id"]), reverse=True)
    out = {"updated": _latest_patch_date(data_dir), "patches": index}
    with open(data_dir / "patches_index.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)


def _latest_patch_date(data_dir: pathlib.Path) -> str:
    """Deterministic freshness marker: the newest patch date in the archive."""
    latest = "2016-05-01"
    for site in ("en", "cn"):
        for patch_file in (data_dir / "patches" / site).glob("*.json"):
            try:
                data = json.loads(patch_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("date", "") > latest:
                latest = data["date"]
    return f"{latest}T00:00:00Z"


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_pair_result(data_dir: pathlib.Path, result: PairResult) -> None:
    with open(data_dir / "patch_pairs.json", "w", encoding="utf-8") as fh:
        json.dump({
            "pairs": result.pairs,
            "unpaired_en": result.unpaired_en,
            "unpaired_cn": result.unpaired_cn,
        }, fh, ensure_ascii=False, indent=1)
