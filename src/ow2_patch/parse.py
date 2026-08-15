"""Parse Overwatch patch notes HTML (EN + CN share the same DOM classes) into Patch objects.

The NetEase (CN) pages contain unclosed <div> tags, which makes tree-based patch
discovery unreliable. We therefore split the HTML *textually* at patch/section opening
tags, then parse each slice independently — cross-boundary contamination is impossible
regardless of malformed nesting. Legacy pages (OW1 era) without the modern section
structure degrade to a single raw_text blob so content is never lost.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from .model import AbilityUpdate, Change, GenericBlock, HeroUpdate, Patch, Perk, Section

ROLE_MAP = {
    "Tank": "tank",
    "Damage": "damage",
    "Support": "support",
    "重装": "tank",
    "输出": "damage",
    "支援": "support",
}

_EN_PERK_RE = re.compile(r"^(.*?)\s*[-–]\s*(Minor|Major) Perk\s*$", re.I)
_CN_PERK_RE = re.compile(r"^(.*?)——(主要|次级)威能\s*$")
_CN_TITLE_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_EN_NUM_RE = re.compile(
    r"(\w[\w ]+?) (increased|reduced|decreased|changed) from (\d+(?:\.\d+)?) to (\d+(?:\.\d+)?)",
    re.I,
)
_CN_NUM_RE = re.compile(
    r"([\u4e00-\u9fff]+)从(\d+(?:\.\d+)?)[点秒米度%]?(提高|缩短|降低|减少|增加|扩大|延长)至(\d+(?:\.\d+)?)[点秒米度%]?"
)
_CN_METRIC_VERB = re.compile(r"(提高|缩短|降低|减少|增加|扩大|延长)$")

# split at opening tags whose class list contains the exact token "PatchNotes-patch"/"PatchNotes-section"
_PATCH_SPLIT_RE = re.compile(r'(?=<div\s+class="(?:[^"]*\s)?PatchNotes-patch(?:\s|"))')
_SECTION_SPLIT_RE = re.compile(r'(?=<div\s+class="(?:[^"]*\s)?PatchNotes-section(?:\s|"))')


def parse_patch_notes(html: str, site: str, url: str = "") -> list[Patch]:
    """Parse all patches contained in one month page."""
    patches: list[Patch] = []
    for chunk in _PATCH_SPLIT_RE.split(html):
        patch = _parse_patch_chunk(chunk, site, url)
        if patch:
            patches.append(patch)
    # seq within same date
    seen: dict[str, int] = {}
    for patch in patches:
        seen[patch.date] = seen.get(patch.date, 0) + 1
        patch.seq = seen[patch.date]
        patch.id = f"{patch.site}-{patch.date}-{patch.seq}"
    return patches


def _parse_patch_chunk(chunk: str, site: str, url: str) -> Patch | None:
    if "PatchNotes-patch" not in chunk:
        return None
    soup = BeautifulSoup(chunk, "lxml")
    title_el = soup.select_one(".PatchNotes-patchTitle") or soup.find(["h1", "h2", "h3"])
    title = _text(title_el)
    if not title:
        return None

    date = _patch_date(soup, title, site)
    if not date:
        return None

    sections = _split_sections(chunk)
    if not sections:
        # drop site chrome (Top-of-post buttons, pagination) from the legacy fallback
        for el in soup.select(".PatchNotesTop, .PatchNotesPagination"):
            el.decompose()
        return Patch(
            site=site, date=date, url=url, title=title,
            raw_text=_normalize_text(soup.get_text(" ", strip=True)),
        )
    return Patch(site=site, date=date, url=url, title=title,
                 sections=[_parse_section(s, site) for s in sections])


def _split_sections(chunk: str) -> list[str]:
    """Textually slice a patch chunk into per-section fragments at section opening tags."""
    parts = _SECTION_SPLIT_RE.split(chunk)
    return [p for p in parts if "PatchNotes-section" in p]


def _patch_date(soup: BeautifulSoup, title: str, site: str) -> str | None:
    anchor = soup.select_one(".anchor[id^='patch-']")
    if anchor:
        m = re.match(r"patch-(\d{4})-(\d{2})-(\d{2})", anchor.get("id", ""))
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    if site == "cn":
        m = _CN_TITLE_DATE_RE.search(title)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def _parse_section(fragment: str, site: str) -> Section:
    soup = BeautifulSoup(fragment, "lxml")
    title = _text(soup.select_one(".PatchNotes-sectionTitle"))
    classes = _first_class(soup)
    is_hero = "PatchNotes-section-hero_update" in (classes or [])

    section = Section(
        type="hero_update" if is_hero else "generic_update",
        title=title,
        role=ROLE_MAP.get(title or ""),
        description=_text(soup.select_one(".PatchNotes-sectionDescription")),
    )
    for hero_div in soup.select(".PatchNotesHeroUpdate"):
        section.heroes.append(_parse_hero(hero_div, section.role, site))
    for block_div in soup.select(".PatchNotesGeneralUpdate"):
        section.blocks.append(_parse_generic_block(block_div))

    if not section.heroes and not section.blocks and section.description is None:
        section.description = _normalize_text(soup.get_text(" ", strip=True)) or None
    return section


def _first_class(soup: BeautifulSoup) -> list[str]:
    sec = soup.find("div", class_="PatchNotes-section")
    return sec.get("class", []) if sec else []


def _parse_hero(hero_div: Tag, role: str | None, site: str) -> HeroUpdate:
    name = _text(hero_div.select_one(".PatchNotesHeroUpdate-name"))
    body = hero_div.select_one(".PatchNotesHeroUpdate-body") or hero_div
    dev_note = _text(body.select_one(".PatchNotes-dev"))

    hero = HeroUpdate(name_en=name if site == "en" else None,
                      name_cn=name if site == "cn" else None,
                      role=role, dev_note=dev_note or None)

    general_div = body.select_one(".PatchNotesHeroUpdate-generalUpdates")
    if general_div:
        hero.general, hero.perks = _parse_general_updates(general_div, site)

    abilities_list = body.select_one(".PatchNotesHeroUpdate-abilitiesList")
    if abilities_list:
        for ab_div in abilities_list.select(".PatchNotesAbilityUpdate"):
            hero.abilities.append(_parse_ability(ab_div, site))
    return hero


def _parse_general_updates(div: Tag, site: str) -> tuple[list[str], list[Perk]]:
    general: list[str] = []
    perks: list[Perk] = []
    current: Perk | None = None
    for child in div.children:
        if not isinstance(child, Tag):
            continue
        if child.name == "p":
            text = _text(child)
            perk_name = _perk_name(text, site)
            if perk_name is not None:
                current = Perk(**{f"name_{site}": perk_name})
                perks.append(current)
            elif text and not _is_dev(child):
                general.append(text)
        elif child.name == "ul":
            lines = [_text(li) for li in child.find_all("li")]
            lines = [ln for ln in lines if ln]
            if not lines:
                continue
            if current is not None:
                if site == "en":
                    current.lines_en = lines
                else:
                    current.lines_cn = lines
                current.status = _perk_status(current, site)
                current = None
            else:
                general.extend(lines)
    return general, [p for p in perks if p is not None]


def _perk_name(text: str, site: str) -> str | None:
    if not text:
        return None
    if site == "en":
        m = _EN_PERK_RE.match(text)
        return m.group(1).strip() if m else None
    m = _CN_PERK_RE.match(text)
    return m.group(1).strip() if m else None


def _perk_status(perk: Perk, site: str) -> str:
    lines = perk.lines_en if site == "en" else perk.lines_cn
    for line in lines:
        s = line.strip().rstrip(".")
        if site == "en":
            if s == "Removed":
                return "removed"
            if s == "New":
                return "added"
            if "Reworked" in line:
                return "reworked"
            if "Moved from" in line:
                return "moved"
        else:
            if s == "已移除":
                return "removed"
            if s == "新增":
                return "added"
            if "重做" in line:
                return "reworked"
            if "改为了" in line:
                return "moved"
    return "changed"


def _parse_ability(ab_div: Tag, site: str) -> AbilityUpdate:
    name = _text(ab_div.select_one(".PatchNotesAbilityUpdate-name"))
    ability = AbilityUpdate(**{f"name_{site}": name or None})
    detail = ab_div.select_one(".PatchNotesAbilityUpdate-detailList")
    if detail:
        for li in detail.find_all("li"):
            text = _text(li)
            if not text:
                continue
            change = Change(**{f"text_{site}": text})
            _extract_numbers(change, text, site)
            ability.changes.append(change)
    return ability


def _extract_numbers(change: Change, text: str, site: str) -> None:
    if site == "en":
        m = _EN_NUM_RE.search(text)
        if m:
            change.metric = m.group(1).strip().lower()
            change.before = float(m.group(3))
            change.after = float(m.group(4))
    else:
        m = _CN_NUM_RE.search(text)
        if m:
            change.metric = _CN_METRIC_VERB.sub("", m.group(1))
            change.before = float(m.group(2))
            change.after = float(m.group(4))


def _parse_generic_block(div: Tag) -> GenericBlock:
    title = _text(div.select_one(".PatchNotesGeneralUpdate-title"))
    body = _text(div.select_one(".PatchNotesGeneralUpdate-description"))
    dev = _text(div.select_one(".PatchNotes-dev"))
    if title is None and body is None:
        body = _normalize_text(div.get_text(" ", strip=True)) or None
    return GenericBlock(title=title or None, body=body or None, dev=dev or None)


def _text(el: Tag | None) -> str | None:
    if el is None:
        return None
    return _normalize_text(el.get_text(" ", strip=True)) or None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_dev(el: Tag) -> bool:
    return "dev" in el.get("class", [])
