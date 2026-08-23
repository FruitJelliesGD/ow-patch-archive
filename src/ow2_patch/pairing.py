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

from .pipeline import _is_balance_hero

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_EN_TITLE_DATE_RE = re.compile(r"([A-Z][a-z]{2,8})\s+(\d{1,2}),\s*(\d{4})")
_CN_TITLE_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")

# signature mismatch penalty: larger than any date-based weight (~20M) so a
# same-content 1-day-lag candidate always beats a same-day different page
SIG_PENALTY = 100_000_000


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


def _patch_signature(patch_data: dict) -> str:
    """Normalized structural signature: section types + ordered hero slugs.

    The EN and CN versions of the same logical patch parse into the same
    section/hero structure (hero slugs are cross-language canonical), so equal
    signatures are a strong same-content signal at pairing time — a same-day
    page with different content must not beat the real 1-day-lag partner.

    Trailing empty generic_update sections are stripped (at least one section
    stays): one site may carry an empty "Map Updates"-style stub that the
    other omits (e.g. en-2025-07-03 vs cn-2025-07-09 differ only by one
    trailing generic_update:), and those are not content.
    """
    parts = []
    for s in patch_data.get("sections", []):
        heroes = ",".join(h.get("slug", "") for h in s.get("heroes", []))
        parts.append(f"{s.get('type', '')}:{heroes}")
    while len(parts) > 1 and parts[-1] == "generic_update:":
        parts.pop()
    return "|".join(parts)


def _signature_comparable(sig: str) -> bool:
    """True when a signature carries content signal (any hero slug).

    Two all-generic-empty patches (e.g. Feb-2025's 2-section hotfix vs the
    8-section CN page) have no hero signal to compare; equality would let a
    trivial stub steal a real pairing, so those edges fall back to the
    date-based weights.
    """
    return any(seg.split(":", 1)[1] for seg in sig.split("|") if ":" in seg)


def pair_patches(en: list[dict], cn: list[dict],
                 data_dir: pathlib.Path | None = None) -> PairResult:
    """Maximum-cardinality minimum-weight pairing of EN and CN patches.

    No pre-matching on exact dates: in a 1-day-lag cluster (EN 26..29 vs CN 27..30)
    exact-date pairs would consume the shared dates and strand the tail. The weighted
    matching maximizes the pair count first; the anchor-diff weight term prefers
    same-date pairs whenever that does not cost a match.

    With data_dir set, a structural-signature penalty is added to edges whose EN
    and CN content differs (section types + hero slugs): the same-day bias only
    wins when the same-day page really is the same content. The penalty never
    drops an edge, so maximum cardinality is preserved (a signature-mismatched
    pair still forms when nothing better exists).
    """
    signatures: dict[str, str] = {}
    if data_dir is not None:
        for site in ("en", "cn"):
            for patch_file in (data_dir / "patches" / site).glob("*.json"):
                try:
                    data = json.loads(patch_file.read_text(encoding="utf-8"))
                    signatures[data["id"]] = _patch_signature(data)
                except Exception:
                    continue
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
            # same-day/title-day choices must pass a content check; 1-day-lag
            # partners are trusted on the date weights (the CN side may lack
            # hero sections entirely for some pages, e.g. Season-15's CN page,
            # so strict signature equality can only validate same-day picks)
            if signatures and min(anchor_diff, title_diff) == 0:
                s_en = signatures.get(p["patch_id"])
                s_cn = signatures.get(q["patch_id"])
                # compare only when at least one side carries hero content; two
                # all-generic-empty pages have no content signal to distinguish
                if (s_en is not None and s_cn is not None
                        and (_signature_comparable(s_en) or _signature_comparable(s_cn))
                        and s_en != s_cn):
                    weight += SIG_PENALTY
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


def _hero_has_changes(hero: dict, include_stadium: bool = True) -> bool:
    """True when a balance hero block carries ≥1 change-bearing element — a
    named ability with changes, any perk, a general line with text, or (when
    include_stadium) a stadium item with lines — mirroring what
    build_hero_files emits records for. Stadium-item-only blocks are excluded
    from the structural new_hero signal: a Stadium roster addition is not a
    hero introduction."""
    if any((a.get("name_en") or a.get("name_cn")) and a.get("changes")
           for a in hero.get("abilities", [])):
        return True
    if hero.get("perks") or any(_general_text(g) for g in hero.get("general", [])):
        return True
    if include_stadium and any(il for item in hero.get("stadium_items", [])
                               for il in item.get("lines_en", []) + item.get("lines_cn", [])):
        return True
    return False


def _hero_slugs(data: dict, include_stadium: bool = True) -> set[str]:
    """Slugs of balance hero blocks in a patch that carry change content."""
    slugs: set[str] = set()
    for section in data.get("sections", []):
        for hero in section.get("heroes", []):
            if _is_balance_hero(hero) and hero.get("slug") and _hero_has_changes(hero, include_stadium):
                slugs.add(hero["slug"])
    return slugs


def _has_hero_changes(data: dict) -> bool:
    """True when the patch contributes ≥1 record to the hero balance history
    (stadium mask / item blocks excluded by `_is_balance_hero`)."""
    return bool(_hero_slugs(data))


def _general_text(g) -> str:
    if isinstance(g, str):
        return g
    return g.get("text_en") or g.get("text_cn") or ""


def _content_strings(data: dict) -> list[str]:
    """All text strings of a patch's content (title + sections + raw_text).

    URL strings are skipped so CDN asset paths cannot false-positive a
    category; top-level id/url/site keys are never visited."""
    def walk(v):
        if isinstance(v, str):
            return [] if v.lower().startswith("http") else [v]
        if isinstance(v, dict):
            out: list[str] = []
            for x in v.values():
                out.extend(walk(x))
            return out
        if isinstance(v, list):
            out = []
            for x in v:
                out.extend(walk(x))
            return out
        return []
    out = walk(data.get("sections"))
    out.extend(walk(data.get("raw_text") or ""))
    out.append(data.get("title") or "")
    return out



# structural new_hero signal: a hero is "introduced" by the patch that holds
# its earliest balance record, provided no earlier patch's content mentions the
# hero's name. OW1-era data is unreliable for this (raw_text intros, archive
# start), so the signal is restricted to the structured OW2 era.
_STRUCTURAL_ERA_START = "2022-06-01"


def _build_structural_maps(data_dir: pathlib.Path) -> tuple[dict[str, str], dict[str, str]]:
    """Earliest balance-record date and first content-mention date per hero
    slug, computed from the patch files directly — NOT the heroes/*.json
    artifacts (build_patches_index runs before build_hero_files, so the
    artifacts are stale on the first incremental run that introduces a hero).

    EN names are matched word-bounded (substring matching is fatal: venture ⊂
    adventure, domina ⊂ dominated); CN names as substrings."""
    from .pipeline import _has_cjk

    earliest: dict[str, str] = {}
    name_slugs: dict[str, str] = {}
    content: list[tuple[str, list[str]]] = []
    for site_dir in ("en", "cn"):
        for patch_file in (data_dir / "patches" / site_dir).glob("*.json"):
            try:
                data = json.loads(patch_file.read_text(encoding="utf-8"))
            except OSError:
                continue
            date = data.get("date", "")
            for section in data.get("sections", []):
                for hero in section.get("heroes", []):
                    if not hero.get("slug") or not _is_balance_hero(hero):
                        continue
                    for name in (hero.get("name_en"), hero.get("name_cn")):
                        if name:
                            name_slugs.setdefault(name, hero["slug"])
                    if _hero_has_changes(hero, include_stadium=False):
                        earliest.setdefault(hero["slug"], date)
            content.append((date, _content_strings(data)))

    mention: dict[str, str] = {}
    for name, slug in name_slugs.items():
        if _has_cjk(name):
            hit = min((d for d, strings in content if any(name in s for s in strings)),
                      default=None)
        else:
            rx = re.compile(rf"\b{re.escape(name)}\b", re.I)
            hit = min((d for d, strings in content if any(rx.search(s) for s in strings)),
                      default=None)
        if hit:
            mention[slug] = min(mention.get(slug) or hit, hit)
    return earliest, mention


def _structural_new_hero(
    date: str,
    en_data: dict,
    cn_data: dict,
    earliest: dict[str, str],
    mention: dict[str, str],
) -> bool:
    """True when either side introduces a hero: its earliest balance record and
    its first content mention both land on this patch (structured OW2 era)."""
    if date < _STRUCTURAL_ERA_START:
        return False
    for data in (en_data, cn_data):
        for slug in _hero_slugs(data, include_stadium=False):
            if earliest.get(slug) == date and mention.get(slug) == date:
                return True
    return False


def _load_manual_categories(data_dir: pathlib.Path) -> dict[str, list[str]]:
    """Manual category overrides {index_id: [keys]} from data/manual_categories.json;
    unknown keys are dropped, a missing file is tolerated."""
    from .categories import CATEGORY_ORDER

    path = data_dir / "manual_categories.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    known = set(CATEGORY_ORDER)
    return {pid: [k for k in keys if k in known]
            for pid, keys in raw.items() if isinstance(keys, list)}



def build_patches_index(data_dir: pathlib.Path, result: PairResult) -> None:
    """Write data/patches_index.json: logical patches sorted by date desc.

    Each entry carries a `mode` (see modes): pairs take either side non-standard
    ("either side non-standard wins", en first — the CN April Fools title is
    only reachable via its EN pair), then the official section markers
    (Community Crafted / 社区创造模式) catch standard-titled community-mode
    patches (p-2026-06-30-1); unpaired entries use their own title + sections.

    Each entry also carries `first_section_en`/`first_section_cn` (mirroring
    the `title_*` pattern): the first non-empty section title of that side's
    patch, "" when the patch has no titled sections (e.g. OW1 raw_text pages).
    The time-browser renders it as an at-a-glance content badge.

    Each entry also carries `chars_en`/`chars_cn`: the total character count of
    that side's structured content (all strings inside `sections` plus
    `raw_text`, bilingual fields included — a consistent patch-size proxy).
    The time-browser shows it as "N 字".

    Each entry also carries `categories` (list[str]): content categories
    detected by scanning either side's content under each rule's scope
    (categories.py CATEGORY_SCOPES: whole content for mode categories, title +
    section/block titles for content categories, title + first section for
    season) plus the structural new_hero signal (first-ever balance record and
    first content mention) and the manual overrides file. Display-only — the
    badge shows without reclassifying the patch, so standard-titled mixed
    patches (e.g. p-2026-01-08-1) keep their hero data in the standard history.

    Each entry also carries `has_hero_changes` (bool): whether either side's
    parsed structure contains hero balance-change content (see
    `_has_hero_changes`). Mode-agnostic: special-mode patches carry the flag
    too; the time-browser gates the 「英雄改动」 badge on
    mode == standard AND has_hero_changes.
    """
    from .modes import STANDARD, patch_mode_with_sections
    from .categories import (
        CATEGORY_ORDER,
        HeroContext,
        PatchContext,
        SectionContext,
        categorize_patch,
    )

    overrides = _load_manual_categories(data_dir)
    earliest, mention = _build_structural_maps(data_dir)

    def _load_patch(patch_id: str) -> dict:
        site = patch_id.split("-", 1)[0]
        parts = patch_id.split("-")
        path = data_dir / "patches" / site / f"{'-'.join(parts[1:4])}-{parts[4]}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except OSError:
            return {}

    def _section_titles(data: dict) -> list[str]:
        return [s.get("title") or "" for s in data.get("sections", [])]

    def _first_section(titles: list[str]) -> str:
        return next((t for t in titles if t), "")

    def _content_chars(data: dict) -> int:
        def walk(v):
            if isinstance(v, str):
                return len(v)
            if isinstance(v, dict):
                return sum(walk(x) for x in v.values())
            if isinstance(v, list):
                return sum(walk(x) for x in v)
            return 0
        return walk(data.get("sections")) + walk(data.get("raw_text") or "")

    def _patch_context(data: dict) -> PatchContext:
        sections: list[SectionContext] = []
        for s in data.get("sections", []):
            heroes = [HeroContext(
                stadium_items=bool(h.get("stadium_items")),
                has_changes=bool(h.get("perks"))
                or any(_general_text(g) for g in h.get("general", []))
                or any((a.get("name_en") or a.get("name_cn")) and a.get("changes")
                       for a in h.get("abilities", [])))
                for h in s.get("heroes", [])]
            sections.append(SectionContext(
                title=s.get("title") or "",
                block_titles=[b.get("title") or "" for b in s.get("blocks", [])],
                heroes=heroes))
        titles = [s.title for s in sections]
        return PatchContext(
            title=data.get("title") or "",
            first_section=next((t for t in titles if t), ""),
            sections=sections,
            all_strings=_content_strings(data))

    def _patch_categories(data: dict) -> list[str]:
        return categorize_patch(_patch_context(data))

    def _entry_categories(entry_id: str, date: str, en_data: dict, cn_data: dict) -> list[str]:
        cats = set(_patch_categories(en_data)) | set(_patch_categories(cn_data))
        if _structural_new_hero(date, en_data, cn_data, earliest, mention):
            cats.add("new_hero")
        cats.update(overrides.get(entry_id, []))
        return [k for k in CATEGORY_ORDER if k in cats]

    def _pair_mode(en: dict, cn: dict, en_titles: list[str], cn_titles: list[str]) -> str:
        en_mode = patch_mode_with_sections(en["title"], en_titles)
        if en_mode != STANDARD:
            return en_mode
        return patch_mode_with_sections(cn["title"], cn_titles)

    index: list[dict] = []
    for pair in result.pairs:
        en_data = _load_patch(pair["en"]["patch_id"])
        cn_data = _load_patch(pair["cn"]["patch_id"])
        en_titles = _section_titles(en_data)
        cn_titles = _section_titles(cn_data)
        mode = _pair_mode(pair["en"], pair["cn"], en_titles, cn_titles)
        index.append({
            "id": pair["id"], "date": pair["date"],
            "title_en": pair["en"]["title"], "title_cn": pair["cn"]["title"],
            "first_section_en": _first_section(en_titles),
            "first_section_cn": _first_section(cn_titles),
            "chars_en": _content_chars(en_data),
            "chars_cn": _content_chars(cn_data),
            "url_en": pair["en"]["url"], "url_cn": pair["cn"]["url"],
            "sites": ["en", "cn"],
            "patch_id_en": pair["en"]["patch_id"], "patch_id_cn": pair["cn"]["patch_id"],
            "mode": mode,
            "categories": _entry_categories(pair["id"], pair["date"], en_data, cn_data),
            "has_hero_changes": _has_hero_changes(en_data) or _has_hero_changes(cn_data),
        })
    for patch_id in result.unpaired_en + result.unpaired_cn:
        site = patch_id.split("-", 1)[0]
        parts = patch_id.split("-")
        date_str = "-".join(parts[1:4])
        seq = parts[4]
        meta = _load_patch(patch_id)
        titles = _section_titles(meta)
        first_section = _first_section(titles)
        chars = _content_chars(meta)
        index.append({
            "id": patch_id, "date": date_str,
            "title_en": meta["title"] if site == "en" else None,
            "title_cn": meta["title"] if site == "cn" else None,
            "first_section_en": first_section if site == "en" else None,
            "first_section_cn": first_section if site == "cn" else None,
            "chars_en": chars if site == "en" else None,
            "chars_cn": chars if site == "cn" else None,
            "url_en": meta["url"] if site == "en" else None,
            "url_cn": meta["url"] if site == "cn" else None,
            "sites": [site],
            "patch_id_en": patch_id if site == "en" else None,
            "patch_id_cn": patch_id if site == "cn" else None,
            "mode": patch_mode_with_sections(meta["title"], titles),
            "categories": _entry_categories(patch_id, date_str, meta, {}),
            "has_hero_changes": _has_hero_changes(meta),
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
