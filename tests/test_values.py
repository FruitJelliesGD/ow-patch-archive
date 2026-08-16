"""Value series tests."""

from __future__ import annotations

from ow2_patch.values import build_values


def base_ability(ability_slug="heavy-pulse-rifle", metric="damage", date="2026-06-17",
                 before=19.0, after=18.0):
    return {"kind": "ability", "ability_slug": ability_slug, "metric": metric,
            "date": date, "before": before, "after": after}


def test_after_chain_in_date_order():
    timeline = [
        base_ability(date="2025-11-12", before=18.0, after=19.0),
        base_ability(date="2026-06-17", before=19.0, after=18.0),
        base_ability(date="2024-12-17", before=19.0, after=20.0),
    ]
    values = build_values(timeline)
    points = values["heavy-pulse-rifle:damage"]
    assert [p["value"] for p in points] == [20.0, 19.0, 18.0]
    assert [p["date"] for p in points] == ["2024-12-17", "2025-11-12", "2026-06-17"]


def test_same_date_collapses_to_last_value():
    timeline = [
        base_ability(date="2026-06-17", before=19.0, after=18.0),
        base_ability(date="2026-06-17", before=18.0, after=17.0),
    ]
    points = build_values(timeline)["heavy-pulse-rifle:damage"]
    assert points == [{"date": "2026-06-17", "value": 17.0}]


def test_by_pct_and_missing_skip_series():
    timeline = [
        base_ability(),
        {"kind": "ability", "ability_slug": "sprint", "metric": "move_speed",
         "date": "2026-01-01", "before": None, "after": None, "by_pct": 10.0},
        {"kind": "general", "dimension": "other", "date": "2026-01-01",
         "before": 1.0, "after": 2.0},
    ]
    values = build_values(timeline)
    assert "sprint:move_speed" not in values
    assert "attr:other:value" not in values
    assert "heavy-pulse-rifle:damage" in values


def test_hero_attr_series_key():
    timeline = [
        {"kind": "general", "dimension": "hero_attr", "subject": "health",
         "metric": "health", "date": "2023-02-07", "before": 200.0, "after": 250.0},
    ]
    values = build_values(timeline)
    assert values["attr:health:health"] == [{"date": "2023-02-07", "value": 250.0}]


def test_empty_timeline():
    assert build_values([]) == {}
