"""Parser tests against frozen HTML fixtures captured from the live sites."""

from __future__ import annotations

import pathlib

from ow2_patch.parse import parse_patch_notes

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name: str, site: str):
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return parse_patch_notes(html, site, url=f"https://example/{name}")


def test_en_2026_08_patch_ids_and_sections():
    patches = load("en_2026_08.html", "en")
    assert [p.id for p in patches] == ["en-2026-08-14-1", "en-2026-08-12-1"]
    p = patches[0]
    assert p.date == "2026-08-14"
    assert p.title.startswith("Overwatch Retail Patch Notes")
    assert [s.type for s in p.sections] == ["generic_update", "hero_update"]
    assert p.sections[0].title == "Hotfix Update"
    assert "Replay codes" in p.sections[0].description


def test_en_heroes_abilities_and_numbers():
    patches = load("en_2026_08.html", "en")
    heroes = patches[0].sections[1].heroes
    assert [h.name_en for h in heroes] == ["D.Mon", "Jetpack Cat"]

    dmon = heroes[0]
    assert any("Portable Fusion Repeater" in g for g in dmon.general)
    assert "Hitbox Changes" in dmon.general  # paragraph inside general updates
    surge = dmon.abilities[0]
    assert surge.name_en == "Surging Strike"
    c = surge.changes[0]
    assert c.text_en == "Cast Time reduced from 0.15 to 0.05 seconds."
    assert (c.before, c.after) == (0.15, 0.05)
    assert c.metric == "cast time"

    # "25% to 40%" does not match "from X to Y": text kept, numbers null
    purr = heroes[1].abilities[0].changes[0]
    assert purr.text_en == "Self healing penalty increased from 25% to 40%."
    assert purr.before is None and purr.after is None


def test_cn_2026_08_patch_ids_and_names():
    patches = load("cn_2026_08.html", "cn")
    assert [p.id for p in patches] == ["cn-2026-08-15-1", "cn-2026-08-13-1"]
    p = patches[0]
    assert p.date == "2026-08-15"
    assert p.title == "《守望先锋》补丁说明——2026年8月15日"

    heroes = p.sections[1].heroes
    assert heroes[0].name_cn == "D.Mon"
    ab = heroes[0].abilities[0]
    assert ab.name_cn == "突进刺击"
    c = ab.changes[0]
    assert c.text_cn == "施放时间从0.15秒缩短至0.05秒。"
    assert (c.before, c.after) == (0.15, 0.05)
    assert c.metric == "施放时间"

    p2 = patches[1]
    assert p2.sections[1].heroes[0].abilities[0].name_cn == "等离子剑"
    c2 = p2.sections[1].heroes[0].abilities[0].changes[0]
    assert c2.text_cn == "伤害从60点提高至65点。"
    assert (c2.before, c2.after) == (60.0, 65.0)
    assert c2.metric == "伤害"


def test_legacy_2016_degrades_to_raw_text():
    patches = load("en_2016_05.html", "en")
    assert len(patches) == 1
    p = patches[0]
    assert p.date == "2016-05-27"
    assert p.sections == []
    assert p.raw_text and "ForceFMA" in p.raw_text


def test_same_day_multiple_patches_get_seq():
    patches = load("en_same_day_multi.html", "en")
    assert [p.id for p in patches] == ["en-2026-08-14-1", "en-2026-08-14-2"]


def test_en_perks_and_roles():
    patches = load("en_2026_08_11.html", "en")
    p = patches[0]
    by_hero = {h.name_en: h for s in p.sections for h in s.heroes}

    cassidy = by_hero["Cassidy"]
    assert {x.name_en: x.status for x in cassidy.perks} == {
        "Even the Odds": "removed",
        "Giddy Up": "added",
    }
    giddy = next(x for x in cassidy.perks if x.name_en == "Giddy Up")
    assert giddy.lines_en[0] == "New"
    assert "60% movement speed" in giddy.lines_en[1]

    echo = by_hero["Echo"]
    assert next(x for x in echo.perks if x.name_en == "Focused Rush").status == "moved"

    tank = next(s for s in p.sections if s.role == "tank")
    assert tank.type == "hero_update"
    assert "Domina" in [h.name_en for h in tank.heroes]


def test_cn_perks_status():
    patches = load("cn_2026_08_12.html", "cn")
    p = patches[0]
    by_hero = {h.name_cn: h for s in p.sections for h in s.heroes}

    assert {x.name_cn: x.status for x in by_hero["卡西迪"].perks} == {
        "绝处逢生": "removed",
        "得儿驾": "added",
    }
    assert next(x for x in by_hero["回声"].perks if x.name_cn == "聚焦机动").status == "moved"
    # role mapping for Chinese section titles
    assert by_hero["金驭"].role == "tank"
    assert by_hero["卡西迪"].role == "damage"
    assert by_hero["飞天猫"].role == "support"


def test_invariant_original_text_always_kept():
    for name, site in [
        ("en_2026_08.html", "en"),
        ("cn_2026_08.html", "cn"),
        ("en_2026_08_11.html", "en"),
        ("cn_2026_08_12.html", "cn"),
    ]:
        for patch in load(name, site):
            for s in patch.sections:
                for h in s.heroes:
                    for a in h.abilities:
                        for c in a.changes:
                            assert c.text_en or c.text_cn
