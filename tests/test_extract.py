"""Table-driven tests for extract.py numeric sentence extraction."""

from __future__ import annotations

import pytest

from ow2_patch.extract import apply_extraction, extract_change, normalize_metric


@pytest.mark.parametrize("text,before,after,by,by_pct,metric,unit", [
    # EN from X to Y (existing shape)
    ("Damage increased from 60 to 65.", 60.0, 65.0, 5.0, None, "damage", None),
    ("Cooldown reduced from 13 to 12 seconds.", 13.0, 12.0, -1.0, None, "cooldown", "s"),
    ("Cast Time reduced from 0.3 to 0.2 seconds.", 0.3, 0.2, -0.1, None, "cast_time", "s"),
    # EN noun-separated from-to (previously missed: 'from 75 armor to 50 armor')
    ("Armor over-heal reduced from 75 armor to 50 armor.", 75.0, 50.0, -25.0, None, "armor", "hp"),
    ("Barrier health increased from 450 to 500.", 450.0, 500.0, 50.0, None, "barrier", "hp"),
    # EN to X (Up/Down from Y)
    ("Cost increased to 12000 (Up from 11000).", 11000.0, 12000.0, 1000.0, None, "cost", None),
    ("Base pull speed reduced to 25 meters per second (Down from 30).",
     30.0, 25.0, -5.0, None, "base pull speed", None),
    # EN by X%
    ("Ultimate charge generation rate increased by 20%.", None, None, None, 20.0, "ultimate_cost", None),
    ("Attach angle reduced by 37%.", None, None, None, 37.0, "attach angle", None),
    # EN bare 'reduced 10%' (no 'by')
    ("Ultimate cost reduced 10%.", None, None, None, 10.0, "ultimate_cost", None),
    # EN meters down to
    ("Fusion Cannons spread reduced from 3.75 meters down to 3.375 meters.",
     3.75, 3.375, -0.375, None, "fusion cannons spread", "m"),
    # CN from X to Y
    ("伤害从60点提高至65点。", 60.0, 65.0, 5.0, None, "damage", "hp"),
    ("冷却时间从6秒缩短至4秒。", 6.0, 4.0, -2.0, None, "cooldown", "s"),
    ("移动速度加成从40%降低至30%。", 40.0, 30.0, -10.0, None, "move_speed", "pct"),
    # CN 由X变为Y / 自X降至Y
    ("最大治疗量由400提高为450。", 400.0, 450.0, 50.0, None, "最大治疗量", None),
    # CN 降低X% (by shape)
    ("移动速度降低20%", None, None, None, 20.0, "move_speed", None),
    ("伤害减少15%", None, None, None, 15.0, "damage", None),
])
def test_extract(text, before, after, by, by_pct, metric, unit):
    result = extract_change(text, "cn" if any("\u4e00" <= c <= "\u9fff" for c in text) else "en")
    assert result.before == before
    assert result.after == after
    assert result.by == by
    assert result.by_pct == by_pct
    assert result.metric == metric
    assert result.unit == unit


def test_no_match_leaves_original_fields_null():
    r = extract_change("Now grants 12 instant healing on trigger.", "en")
    assert r.before is None and r.after is None and r.by_pct is None
    r2 = extract_change("Fixed a bug where Nano Boost was removed.", "en")
    assert r2.metric is None


def test_apply_extraction_updates_dict_but_keeps_text():
    change = {"text_en": "Damage increased from 60 to 65.", "before": None, "after": None}
    apply_extraction(change)
    assert change["before"] == 60.0 and change["after"] == 65.0
    assert change["text_en"] == "Damage increased from 60 to 65."
    assert change["metric"] == "damage"


def test_normalize_metric():
    assert normalize_metric("Damage") == ("damage", None)
    assert normalize_metric("伤害") == ("damage", None)
    assert normalize_metric("冷却时间") == ("cooldown", "s")
    assert normalize_metric("基础生命值") == ("health", "hp")
    assert normalize_metric("Weird Metric") == ("weird metric", None)
