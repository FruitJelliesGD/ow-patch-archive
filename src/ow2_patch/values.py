"""Chronological numeric value series per (entry, metric) for the hero pages.

Only before/after pairs contribute a point (the after value at the patch date);
by-pct shapes have no baseline and are skipped. Same-date entries collapse to the
last value. Purely additive: a missing series never affects entry display.
"""

from __future__ import annotations


def build_values(timeline: list[dict]) -> dict:
    series: dict[str, dict[str, float]] = {}
    for entry in timeline:
        before, after = entry.get("before"), entry.get("after")
        if before is None or after is None:
            continue
        key = _series_key(entry)
        if key is None:
            continue
        series.setdefault(key, {})[entry["date"]] = after
    return {
        key: [{"date": date, "value": value} for date, value in sorted(points.items())]
        for key, points in series.items()
    }


def _series_key(entry: dict) -> str | None:
    metric = entry.get("metric") or "value"
    if entry.get("kind") == "ability":
        slug = entry.get("ability_slug") or entry.get("ability_en") or entry.get("ability_cn")
        return f"{slug}:{metric}" if slug else None
    if entry.get("kind") == "perk":
        slug = entry.get("perk_slug")
        return f"perk:{slug}:{metric}" if slug else None
    if entry.get("kind") == "general" and entry.get("dimension") == "hero_attr":
        subject = entry.get("subject") or "other"
        return f"attr:{subject}:{metric}"
    return None
