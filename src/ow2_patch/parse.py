"""Parse Overwatch patch notes HTML (EN + CN share the same DOM classes) into Patch objects.

The NetEase (CN) pages contain unclosed <div> tags, which makes tree-based patch
discovery unreliable. We therefore split the HTML *textually* at patch/section opening
tags, then parse each slice independently — cross-boundary contamination is impossible
regardless of malformed nesting. Legacy pages (OW1 era) without the modern section
structure are parsed structurally (headings + hero markers + nested lists) so they
render like modern patches; pages that yield no structure degrade to a raw_text blob
so content is never lost.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

from .model import AbilityUpdate, Change, GenericBlock, HeroUpdate, Patch, Perk, Section
from .names import NameResolver

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

# split at opening tags whose class list contains the exact token "PatchNotes-patch"/"PatchNotes-section"
_PATCH_SPLIT_RE = re.compile(r'(?=<div\s+class="(?:[^"]*\s)?PatchNotes-patch(?:\s|"))')
_SECTION_SPLIT_RE = re.compile(r'(?=<div\s+class="(?:[^"]*\s)?PatchNotes-section(?:\s|"))')


def parse_patch_notes(html: str, site: str, url: str = "",
                      resolver: NameResolver | None = None) -> list[Patch]:
    """Parse all patches contained in one month page."""
    patches: list[Patch] = []
    for chunk in _PATCH_SPLIT_RE.split(html):
        patch = _parse_patch_chunk(chunk, site, url, resolver=resolver)
        if patch:
            patches.append(patch)
    # seq within same date
    seen: dict[str, int] = {}
    for patch in patches:
        seen[patch.date] = seen.get(patch.date, 0) + 1
        patch.seq = seen[patch.date]
        patch.id = f"{patch.site}-{patch.date}-{patch.seq}"
    return patches


def _parse_patch_chunk(chunk: str, site: str, url: str,
                       resolver: NameResolver | None = None) -> Patch | None:
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
        legacy = _parse_legacy_chunk(soup, site, resolver)
        if legacy:
            legacy.url = url
            legacy.title = title
            legacy.date = date
            return legacy
        # drop site chrome (Top-of-post buttons, pagination) from the legacy fallback
        for el in soup.select(".PatchNotesTop, .PatchNotesPagination"):
            el.decompose()
        return Patch(
            site=site, date=date, url=url, title=title,
            raw_text=_rich_text(soup),
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
        description=_rich_text(soup.select_one(".PatchNotes-sectionDescription")),
    )
    for hero_div in soup.select(".PatchNotesHeroUpdate"):
        section.heroes.append(_parse_hero(hero_div, section.role, site))
    for block_div in soup.select(".PatchNotesGeneralUpdate"):
        section.blocks.append(_parse_generic_block(block_div))

    if not section.heroes and not section.blocks and section.description is None:
        section.description = _rich_text(soup) or None
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
                      role=role,
                      icon=_icon(hero_div, ".PatchNotesHeroUpdate-icon"),
                      dev_note=dev_note or None)

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
    ability = AbilityUpdate(**{f"name_{site}": name or None},
                            icon=_icon(ab_div, ".PatchNotesAbilityUpdate-icon"))
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
    from .extract import extract_change

    result = extract_change(text, site)
    change.metric = result.metric
    change.before = result.before
    change.after = result.after
    change.by = result.by
    change.by_pct = result.by_pct
    change.raw_metric = result.raw_metric
    change.unit = result.unit


def _parse_generic_block(div: Tag) -> GenericBlock:
    title = _text(div.select_one(".PatchNotesGeneralUpdate-title"))
    body = _rich_text(div.select_one(".PatchNotesGeneralUpdate-description"))
    dev = _text(div.select_one(".PatchNotes-dev"))
    if title is None and body is None:
        body = _rich_text(div) or None
    return GenericBlock(title=title or None, body=body or None, dev=dev or None)


def _text(el: Tag | None) -> str | None:
    if el is None:
        return None
    return _normalize_text(el.get_text(" ", strip=True)) or None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Structure-preserving extraction (paragraphs / lists / line breaks)
# ---------------------------------------------------------------------------

_BLOCK_GROUP_TAGS = {"html", "body", "div", "blockquote", "section", "article", "main",
                     "table", "tbody", "thead", "tr"}
_BLOCK_LINE_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "dt", "dd"}


def _rich_text(el: Tag | None) -> str | None:
    """Serialize block-level content preserving paragraphs, lists and breaks.

    <p>/headings become paragraph lines, <br> a soft line break, <ul>/<ol> items
    "- " prefixed lines (nested lists indented 2 spaces per level). Used for
    generic block bodies, section descriptions and the legacy raw_text fallback
    so multi-line official content survives parsing instead of being flattened.
    """
    if el is None:
        return None
    text = _block_lines(el)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or None


def _block_lines(el, depth: int = 0) -> str:
    """Recursively serialize block-level children of `el` into rich text blocks."""
    blocks: list[str] = []
    for child in el.children:
        if not isinstance(child, Tag):
            continue
        name = child.name
        if name in ("ul", "ol"):
            blocks.append(_list_lines(child, depth))
        elif name in _BLOCK_GROUP_TAGS:
            blocks.append(_block_lines(child, depth))
        elif name in _BLOCK_LINE_TAGS:
            text = _inline_text(child)
            if text:
                blocks.append(("  " * depth) + text)
    return "\n\n".join(b for b in blocks if b)


def _list_lines(list_el: Tag, depth: int = 0) -> str:
    """Serialize a <ul>/<ol> into "- " prefixed lines, nested lists indented."""
    lines: list[str] = []
    for li in list_el.find_all("li", recursive=False):
        text = _li_text(li)
        if text:
            lines.append(("  " * depth) + "- " + text)
        for nested in li.find_all(["ul", "ol"], recursive=False):
            lines.append(_list_lines(nested, depth + 1))
    return "\n".join(lines)


def _li_text(li: Tag) -> str:
    """Inline text of an <li>, excluding any nested list (rendered separately)."""
    parts = []
    for node in li.children:
        if isinstance(node, NavigableString):
            parts.append(str(node))
        elif isinstance(node, Tag) and node.name not in ("ul", "ol"):
            parts.append(_inline_raw(node))
    return _normalize_inline("".join(parts))


def _inline_text(el) -> str:
    """Flatten inline content to text; <br> -> newline; media/list tags skipped."""
    return _normalize_inline(_inline_raw(el))


def _inline_raw(el, in_strong: bool = False) -> str:
    """Concatenate inline content verbatim (spaces between adjacent fragments
    are preserved here; normalization happens once at the top level).

    <strong>/<b> emphasis is encoded as markdown-style **bold** so the web
    renderer and the markdown archive can both restore it. Nested emphasis
    keeps only the outer pair of markers.
    """
    if isinstance(el, Tag) and el.name in ("strong", "b") and not in_strong:
        return "**" + _inline_raw(el, True) + "**"
    parts = []
    for node in el.children:
        if isinstance(node, NavigableString):
            parts.append(str(node))
        elif isinstance(node, Tag):
            name = node.name
            if name == "br":
                parts.append("\n")
            elif name in ("script", "style", "img", "ul", "ol"):
                continue
            elif name in ("strong", "b"):
                marker = "" if in_strong else "**"
                parts.append(marker + _inline_raw(node, True) + marker)
            else:
                parts.append(_inline_raw(node, in_strong))
    return "".join(parts)


def _normalize_inline(text: str) -> str:
    # collapse spaces/tabs/nbsp runs but keep \n (soft breaks) intact; only the
    # outer edges of each line are trimmed so inter-fragment spaces survive
    # (e.g. "<a>Bug Report </a>forum." must stay "Bug Report forum.")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return "\n".join(line.strip() for line in text.split("\n"))


def _icon(el: Tag | None, selector: str) -> str | None:
    """Absolute (http/https) image URL from the first matching <img>, if any."""
    if el is None:
        return None
    img = el.select_one(selector)
    if img is None:
        return None
    src = img.get("src")
    if not src or not src.startswith(("http://", "https://")):
        return None
    return src


def _is_dev(el: Tag) -> bool:
    return "dev" in el.get("class", [])


# ---------------------------------------------------------------------------
# Legacy (OW1-era) structural parsing
# ---------------------------------------------------------------------------

_DEV_NOTE_RE = re.compile(r"^Developer (?:Comments?|Notes?):?\s*", re.I)

# static site boilerplate that OW1 pages repeat verbatim on every patch; it is
# chrome, not patch content, so it is dropped from structured sections (the
# modern parser never sees these paragraphs)
_LEGACY_BOILERPLATE = (
    "A new patch is now live.",
    "Read below to learn about the latest changes.",
    "To share your feedback, please post in the General Discussion forum.",
    "Please note that some changes may not be documented or described in full detail.",
)


def _is_boilerplate(text: str) -> bool:
    return any(text.startswith(phrase) for phrase in _LEGACY_BOILERPLATE)


def _dev_note(text: str) -> str | None:
    """Developer-comment paragraph text, or None when not one.

    Legacy pages use two shapes: "<strong><em>Developer Comments:</em></strong>
    <em>…</em>" and a plain "<em>Developer Comment: …</em>".
    """
    m = _DEV_NOTE_RE.match(text)
    if not m:
        return None
    return text[m.end():].strip() or None


def _lead_strong(p: Tag) -> str | None:
    """Text of a paragraph whose FIRST inline child is a <strong>/<b> marker
    (the strong may wrap a colored <span>/<font>, or be wrapped by one).

    Legacy hero/category markers are "<p><strong>Name</strong></p>"; plain
    paragraphs and dev notes (em after the strong) are excluded.
    """
    for child in p.children:
        if isinstance(child, NavigableString):
            if child.strip():
                return None  # real text before any strong: not a marker
            continue
        if isinstance(child, Tag):
            if child.name in ("strong", "b"):
                return _normalize_inline(child.get_text(" ", strip=True)) or None
            if child.name in ("font", "span"):
                strong = child.find(["strong", "b"])
                if strong is not None:
                    return _normalize_inline(strong.get_text(" ", strip=True)) or None
            return None
    return None


def _legacy_content_elements(el) -> list[Tag]:
    """Flatten unclassed container divs so the content (h1/p/h2/ul) is walked
    directly; classed chrome divs (anchor/labels/Top) stay as markers to skip."""
    out: list[Tag] = []
    for child in el.children:
        if not isinstance(child, Tag):
            continue
        if child.name == "div" and not child.get("class"):
            out.extend(_legacy_content_elements(child))
        else:
            out.append(child)
    return out


def _parse_legacy_chunk(soup: BeautifulSoup, site: str,
                        resolver: NameResolver | None) -> Patch | None:
    """Structurally parse an OW1-era patch into modern sections/heroes/blocks.

    Returns None when the page has no usable structure (caller falls back to
    the raw_text blob). The hero table decides whether a <strong> marker is a
    hero block ("Ana") or a category block ("Heroes", "New Hero: Ana").
    """
    if resolver is None:
        resolver = NameResolver()
    wrapper = soup.select_one(".PatchNotes-patch")
    if wrapper is None:
        return None
    for el in soup.select(".PatchNotesTop, .PatchNotesPagination"):
        el.decompose()

    sections: list[Section] = []
    sec: Section | None = None
    hero: HeroUpdate | None = None
    block: GenericBlock | None = None
    block_paras: list[str] = []
    pending_ability: AbilityUpdate | None = None
    seen_title = False
    for el in _legacy_content_elements(wrapper):
        if not isinstance(el, Tag):
            continue
        if el.name == "div" and el.get("class") and (
                {"anchor", "PatchNotes-labels", "PatchNotesTop"} & set(el.get("class", []))):
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            text = _text(el)
            if not text:
                continue
            if not seen_title:
                seen_title = True  # first heading is the patch title (already parsed)
                continue
            sec = Section(title=text)
            hero = block = None
            block_paras = []
            pending_ability = None
            sections.append(sec)
            continue
        if el.name == "p":
            text = _text(el)
            if not text or _is_boilerplate(text):
                continue
            dev = _dev_note(text)
            if dev is not None:
                if hero is not None:
                    hero.dev_note = dev
                elif block is not None:
                    block.dev = dev
                continue
            lead = _lead_strong(el)
            if lead is not None:
                if sec is None:
                    sec = Section(title="")
                    sections.append(sec)
                if resolver.is_known_hero(lead, "en"):
                    hero = HeroUpdate(name_en=lead)
                    block = None
                    block_paras = []
                    pending_ability = None
                    sec.heroes.append(hero)
                else:
                    # category marker ("Heroes", "General") or featured block
                    block = GenericBlock(title=lead or None)
                    hero = None
                    block_paras = []
                    pending_ability = None
                    rest = text[len(lead):].strip()
                    if rest:  # e.g. "New Hero: Ana (Support)" followed by its intro
                        block_paras.append(rest)
                        block.body = rest
                    sec.blocks.append(block)
                continue
            # plain paragraph: ability name (2019 format, followed by its <ul>),
            # a block's body paragraph, or a section intro
            if sec is None:
                sec = Section(title="")
                sections.append(sec)
            nxt = el.find_next_sibling()
            if hero is not None and isinstance(nxt, Tag) and nxt.name == "ul":
                pending_ability = AbilityUpdate(**{f"name_{site}": text})
                hero.abilities.append(pending_ability)
            elif block is not None:
                block_paras.append(text)
                block.body = "\n\n".join(block_paras)
            else:
                sec.description = "\n\n".join(
                    [p for p in [sec.description, text] if p])
            continue
        if el.name == "ul":
            if sec is None:
                sec = Section(title="")
                sections.append(sec)
            if pending_ability is not None:
                _collect_changes(el, pending_ability, site)
                pending_ability = None
            elif hero is not None:
                _parse_hero_list(el, hero, site)
            elif block is not None:
                block.body = "\n\n".join(
                    [p for p in [block.body, _list_lines(el)] if p])
            else:
                sec.description = "\n\n".join(
                    [p for p in [sec.description, _list_lines(el)] if p])
    if not sections:
        return None
    for s in sections:
        s.type = "hero_update" if s.heroes else "generic_update"
    return Patch(site=site, sections=sections)


def _li_name(li: Tag) -> str | None:
    """Single-line text of an <li> (nested list excluded), for ability names."""
    text = _li_text(li)
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip() or None


def _parse_hero_list(ul: Tag, hero: HeroUpdate, site: str) -> None:
    """Legacy hero list: top-level <li> with a nested <ul> is an ability (its
    leaf lines become the changes; sub-heading names like "Primary Fire" are
    dropped, matching the modern _parse_ability); a bare <li> is a general line.
    """
    for li in ul.find_all("li", recursive=False):
        sub = li.find("ul", recursive=False)
        if sub is not None:
            ability = AbilityUpdate(**{f"name_{site}": _li_name(li)})
            _collect_changes(sub, ability, site)
            hero.abilities.append(ability)
        else:
            text = _li_text(li)
            if text:
                hero.general.append(text)


def _collect_changes(ul: Tag, ability: AbilityUpdate, site: str) -> None:
    for li in ul.find_all("li", recursive=False):
        sub = li.find("ul", recursive=False)
        if sub is not None:
            _collect_changes(sub, ability, site)
            continue
        text = _li_text(li)
        if not text:
            continue
        change = Change(**{f"text_{site}": text})
        _extract_numbers(change, text, site)
        ability.changes.append(change)
