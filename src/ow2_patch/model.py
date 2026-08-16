"""Data model for parsed Overwatch patch notes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Change:
    """A single change line. Original text is always kept (at least one locale).

    Derived fields (before/after/by/by_pct/metric/unit) are extraction results and
    are excluded from content hashing.
    """

    text_en: str | None = None
    text_cn: str | None = None
    before: float | None = None
    after: float | None = None
    by: float | None = None       # derived delta after-before (from X to Y shapes)
    by_pct: float | None = None   # "by X%"/"降低X%" without a baseline
    metric: str | None = None     # normalized metric key (damage/cooldown/...)
    raw_metric: str | None = None  # original metric phrase, for traceability
    unit: str | None = None        # normalized unit (s/m/hp/deg/pct)


@dataclass
class AbilityUpdate:
    name_en: str | None = None
    name_cn: str | None = None
    slug: str = ""
    changes: list[Change] = field(default_factory=list)


@dataclass
class Perk:
    """A hero perk (威能) block: name, fate (added/removed/reworked/moved/changed) and lines."""

    name_en: str | None = None
    name_cn: str | None = None
    status: str = "changed"
    lines_en: list[str] = field(default_factory=list)
    lines_cn: list[str] = field(default_factory=list)
    raw_text: list[str] = field(default_factory=list)  # original general lines before attribution


@dataclass
class HeroUpdate:
    slug: str = ""
    name_en: str | None = None
    name_cn: str | None = None
    role: str | None = None
    dev_note: str | None = None
    general: list[str] = field(default_factory=list)
    perks: list[Perk] = field(default_factory=list)
    abilities: list[AbilityUpdate] = field(default_factory=list)


@dataclass
class GenericBlock:
    """A titled body block inside a generic section (e.g. a map update, a stadium item)."""

    title: str | None = None
    body: str | None = None
    dev: str | None = None


@dataclass
class Section:
    type: str = "generic_update"  # hero_update | generic_update
    title: str | None = None
    role: str | None = None
    description: str | None = None
    heroes: list[HeroUpdate] = field(default_factory=list)
    blocks: list[GenericBlock] = field(default_factory=list)


@dataclass
class Patch:
    id: str = ""
    site: str = ""
    date: str = ""  # YYYY-MM-DD
    url: str = ""
    title: str = ""
    seq: int = 1
    sections: list[Section] = field(default_factory=list)
    raw_text: str | None = None  # fallback when page structure is unrecognized
    hash: str = ""


def patch_to_dict(patch: Patch) -> dict:
    """Deterministic dict representation used for storage, hashing and diffing."""
    return {
        "id": patch.id,
        "site": patch.site,
        "date": patch.date,
        "url": patch.url,
        "title": patch.title,
        "seq": patch.seq,
        "sections": [_section_to_dict(s) for s in patch.sections],
        "raw_text": patch.raw_text,
        "hash": patch.hash,
    }


def _section_to_dict(s: Section) -> dict:
    return {
        "type": s.type,
        "title": s.title,
        "role": s.role,
        "description": s.description,
        "heroes": [_hero_to_dict(h) for h in s.heroes],
        "blocks": [_block_to_dict(b) for b in s.blocks],
    }


def _hero_to_dict(h: HeroUpdate) -> dict:
    return {
        "slug": h.slug,
        "name_en": h.name_en,
        "name_cn": h.name_cn,
        "role": h.role,
        "dev_note": h.dev_note,
        "general": h.general,
        "perks": [_perk_to_dict(p) for p in h.perks],
        "abilities": [_ability_to_dict(a) for a in h.abilities],
    }


def _perk_to_dict(p: Perk) -> dict:
    return {
        "name_en": p.name_en,
        "name_cn": p.name_cn,
        "status": p.status,
        "lines_en": p.lines_en,
        "lines_cn": p.lines_cn,
        "raw_text": p.raw_text,
    }


def _ability_to_dict(a: AbilityUpdate) -> dict:
    return {
        "name_en": a.name_en,
        "name_cn": a.name_cn,
        "slug": a.slug,
        "changes": [_change_to_dict(c) for c in a.changes],
    }


def _change_to_dict(c: Change) -> dict:
    return {
        "text_en": c.text_en,
        "text_cn": c.text_cn,
        "before": c.before,
        "after": c.after,
        "by": c.by,
        "by_pct": c.by_pct,
        "metric": c.metric,
        "raw_metric": c.raw_metric,
        "unit": c.unit,
    }


def _block_to_dict(b: GenericBlock) -> dict:
    return {"title": b.title, "body": b.body, "dev": b.dev}
