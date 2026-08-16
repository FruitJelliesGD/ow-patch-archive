"""Structured extraction of numeric change facts from patch-note text.

Covers the sentence shapes that actually appear in the archive:
  EN: "X increased from 60 to 65.", "X reduced to 18 (Down from 19).",
      "X increased by 15%", "X reduced 10%", "X changed to 3.5 meters down to 3.0"
  CN: "伤害从60点提高至65点。", "冷却时间缩短至4秒", "移动速度降低20%"

Extraction is a *derivation* layer: it never alters original text, and its results
are excluded from content hashes so upgrading patterns does not look like official
edits. by-X% shapes have no baseline, so they store `by_pct` and leave before/after
null instead of inventing a baseline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_EN_FROM_TO_RE = re.compile(
    r"([\w][\w -]*?) (increased|reduced|decreased|changed|lowered|raised) from "
    r"(\d+(?:\.\d+)?)(?: ([a-z]+))? to (\d+(?:\.\d+)?)",
    re.I,
)
_EN_UP_FROM_RE = re.compile(
    r"([\w][\w -]*?) (increased|reduced) to (\d+(?:\.\d+)?)(?: [a-z/ ]+?)? "
    r"\((?P<d>up|down) from (\d+(?:\.\d+)?)\)",
    re.I,
)
_EN_BY_PCT_RE = re.compile(
    r"([\w][\w -]*?) (increased|reduced|decreased|lowered|raised) by (\d+(?:\.\d+)?)%",
    re.I,
)
_EN_BARE_PCT_RE = re.compile(
    r"([\w][\w -]*?) (increased|reduced|decreased|lowered|raised) (\d+(?:\.\d+)?)%",
    re.I,
)
_EN_DOWN_TO_RE = re.compile(
    r"([\w][\w -]*?) (?:reduced|decreased|lowered|changed)[^.]*? "
    r"(\d+(?:\.\d+)?) meters down to (\d+(?:\.\d+)?)",
    re.I,
)

_CN_VERBS = "提高|提升|上调|缩短|降低|减少|下调|削减|增加|扩大|延长|降至|改为|变为"
_CN_FROM_TO_RE = re.compile(
    rf"([\u4e00-\u9fff]+?)(?:从|由|自)(\d+(?:\.\d+)?)([点秒米度%])?(?:{_CN_VERBS})(?:至|为)(\d+(?:\.\d+)?)([点秒米度%])?"
)
_CN_BY_PCT_RE = re.compile(
    rf"([\u4e00-\u9fff]+?)(?:{_CN_VERBS})(\d+(?:\.\d+)?)%"
)
_CN_UNIT = {"点": "hp", "秒": "s", "米": "m", "度": "deg", "%": "pct"}

# raw metric (EN lowercase words / CN phrase) -> (canonical metric, unit)
_METRIC_ALIASES = {
    "damage": ("damage", None), "伤害": ("damage", None), "基础伤害": ("damage", None),
    "health": ("health", "hp"), "生命值": ("health", "hp"), "基础生命值": ("health", "hp"),
    "生命": ("health", "hp"), "治疗量": ("healing", None), "healing": ("healing", None),
    "ultimate cost": ("ultimate_cost", None), "ultimate charge": ("ultimate_cost", None),
    "终极技能消耗": ("ultimate_cost", None), "终极技能充能": ("ultimate_cost", None),
    "movement speed": ("move_speed", "m/s"), "移动速度": ("move_speed", "m/s"),
    "cast time": ("cast_time", "s"), "施放时间": ("cast_time", "s"),
    "cooldown": ("cooldown", "s"), "冷却时间": ("cooldown", "s"),
    "range": ("range", "m"), "射程": ("range", "m"), "半径": ("range", "m"),
    "ammo": ("ammo", None), "弹药": ("ammo", None), "弹药量": ("ammo", None),
    "projectile speed": ("projectile_speed", "m/s"), "弹道速度": ("projectile_speed", "m/s"),
    "rate of fire": ("rate_of_fire", None), "射速": ("rate_of_fire", None),
    "armor": ("armor", "hp"), "护甲": ("armor", "hp"),
    "shield": ("shield", "hp"), "护盾": ("shield", "hp"), "护盾值": ("shield", "hp"),
    "barrier": ("barrier", "hp"), "屏障": ("barrier", "hp"),
    "overhealth": ("overhealth", "hp"), "过量生命值": ("overhealth", "hp"),
    "knockback": ("knockback", None), "击退": ("knockback", None),
    "blast radius": ("blast_radius", "m"), "爆炸半径": ("blast_radius", "m"),
    "recovery": ("recovery", "s"), "恢复时间": ("recovery", "s"),
    "duration": ("duration", "s"), "持续时间": ("duration", "s"),
    "travel speed": ("travel_speed", "m/s"),
    "health per second": ("hps", "hp/s"), "治疗量/秒": ("hps", "hp/s"),
}

_UNIT_ALIASES = {
    "seconds": "s", "second": "s", "sec": "s", "秒": "s",
    "meters": "m", "meter": "m", "metres": "m", "米": "m",
    "points": "hp", "points.": "hp", "点": "hp",
    "度": "deg", "degrees": "deg", "degree": "deg",
}


@dataclass
class Extracted:
    metric: str | None = None
    before: float | None = None
    after: float | None = None
    by: float | None = None
    by_pct: float | None = None
    unit: str | None = None
    raw_metric: str | None = None


def extract_change(text: str, site: str) -> Extracted:
    if site == "cn":
        return _extract_cn(text)
    return _extract_en(text)


def _extract_en(text: str) -> Extracted:
    m = _EN_FROM_TO_RE.search(text)
    if m:
        before, after = float(m.group(3)), float(m.group(5))
        raw = m.group(1).strip().lower()
        unit = _UNIT_ALIASES.get((m.group(4) or "").lower().rstrip("."))
        return _fill(Extracted(before=before, after=after, by=round(after - before, 4),
                               raw_metric=raw, unit=unit), raw)
    m = _EN_UP_FROM_RE.search(text)
    if m:
        before, after = float(m.group(5)), float(m.group(3))
        raw = m.group(1).strip().lower()
        return _fill(Extracted(before=before, after=after, by=round(after - before, 4),
                               raw_metric=raw), raw)
    m = _EN_BY_PCT_RE.search(text)
    if m:
        raw = m.group(1).strip().lower()
        return _fill(Extracted(by_pct=float(m.group(3)), raw_metric=raw), raw)
    m = _EN_BARE_PCT_RE.search(text)
    if m:
        raw = m.group(1).strip().lower()
        return _fill(Extracted(by_pct=float(m.group(3)), raw_metric=raw), raw)
    m = _EN_DOWN_TO_RE.search(text)
    if m:
        before, after = float(m.group(2)), float(m.group(3))
        raw = m.group(1).strip().lower()
        return _fill(Extracted(before=before, after=after, by=round(after - before, 4),
                               unit="m", raw_metric=raw), raw)
    return Extracted()


def _extract_cn(text: str) -> Extracted:
    m = _CN_FROM_TO_RE.search(text)
    if m:
        before, after = float(m.group(2)), float(m.group(4))
        raw = m.group(1)
        unit = _CN_UNIT.get(m.group(3) or "") or _CN_UNIT.get(m.group(5) or "")
        return _fill(Extracted(before=before, after=after, by=round(after - before, 4),
                               unit=unit, raw_metric=raw), raw)
    m = _CN_BY_PCT_RE.search(text)
    if m:
        raw = m.group(1)
        return _fill(Extracted(by_pct=float(m.group(2)), raw_metric=raw), raw)
    return Extracted()


def _fill(result: Extracted, raw: str) -> Extracted:
    metric, unit = normalize_metric(raw)
    result.metric = metric
    if result.by_pct is not None:
        result.unit = None  # percentage deltas carry no physical unit
    elif result.unit is None:
        result.unit = unit
    return result


def normalize_metric(raw: str) -> tuple[str | None, str | None]:
    """Map a raw metric phrase to (canonical metric, unit); unknown stays as-is."""
    if not raw:
        return None, None
    key = raw.strip().lower().rstrip(".").rstrip("：")
    entry = _METRIC_ALIASES.get(key)
    if entry:
        return entry
    for phrase, (metric, unit) in _METRIC_ALIASES.items():
        if phrase and key.startswith(phrase):
            return metric, unit
    return key, None


def apply_extraction(change: dict) -> None:
    """In-place update of a stored change dict's derived fields (text untouched)."""
    text = change.get("text_en") or change.get("text_cn") or ""
    site = "en" if change.get("text_en") else "cn"
    result = extract_change(text, site)
    for field in ("metric", "before", "after", "by", "by_pct", "unit", "raw_metric"):
        change[field] = getattr(result, field)
