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
    assert c.metric == "cast_time"  # normalized from 'cast time'

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
    assert c.metric == "cast_time"  # normalized from 施放时间

    p2 = patches[1]
    assert p2.sections[1].heroes[0].abilities[0].name_cn == "等离子剑"
    c2 = p2.sections[1].heroes[0].abilities[0].changes[0]
    assert c2.text_cn == "伤害从60点提高至65点。"
    assert (c2.before, c2.after) == (60.0, 65.0)
    assert c2.metric == "damage"


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


def test_en_block_body_preserves_structure():
    """Generic block bodies keep paragraphs and list items instead of being
    flattened to a single space-joined string."""
    patches = load("en_2026_08_11.html", "en")
    p = patches[0]
    blocks = {b.title: b for s in p.sections for b in s.blocks}

    revamp = blocks["Battle Pass Revamp"]
    assert "\n\n" in revamp.body  # intro paragraph separated from the bullet list
    assert "\n- **Choose your path" in revamp.body  # "- " prefix + bold lead kept

    subroles = blocks["Subroles"]
    assert subroles.body == "Flanker\n\n- Additional healing from health packs reduced from 75 to 50."


def test_en_strong_emphasis_preserved():
    """<strong> inside block bodies is encoded as **bold** markers."""
    patches = load("en_2026_08_11.html", "en")
    p = patches[0]
    blocks = {b.title: b for s in p.sections for b in s.blocks}
    shooting = blocks["Shooting Star: My MEKA Mania"]
    assert shooting.body.startswith("**Support Your MEKA Faves On A Global Stage!**")
    revamp = blocks["Battle Pass Revamp"]
    assert "- **Choose your path through the Battle Pass.** You no longer" in revamp.body


def test_en_hero_and_ability_icons_captured():
    patches = load("en_2026_08_11.html", "en")
    hero = next(h for s in patches[0].sections for h in s.heroes if h.name_en == "Domina")
    assert hero.icon and hero.icon.startswith("https://") and hero.icon.endswith(".png")
    assert hero.abilities and hero.abilities[0].icon
    assert hero.abilities[0].icon.startswith("https://")


def test_cn_hero_and_ability_icons_captured():
    patches = load("cn_2026_08_12.html", "cn")
    hero = next(h for s in patches[0].sections for h in s.heroes)
    assert hero.icon and "netease" in hero.icon
    assert hero.abilities and "netease" in hero.abilities[0].icon


def test_legacy_raw_text_preserves_line_structure():
    patches = load("en_2016_05.html", "en")
    rt = patches[0].raw_text
    assert rt and "\n\n" in rt  # paragraphs separated by blank lines
    assert "\n- " in rt  # list items keep their "- " markers


def test_legacy_raw_text_keeps_inline_fragment_spacing():
    """Adjacent inline nodes must not lose their separating space, or the
    boilerplate chrome phrases ("Bug Report forum") fail to match at hash time."""
    patches = load("en_2016_05.html", "en")
    rt = patches[0].raw_text
    assert "Bug Report forum" in rt
    assert "Bug Reportforum" not in rt


def test_inline_text_boundaries():
    """Synthetic boundaries for the structure-preserving parser: Latin keeps
    inter-fragment spaces, CJK gains none, <br> stays a soft break."""
    from bs4 import BeautifulSoup

    from ow2_patch.parse import _inline_text

    def inline(html):
        return _inline_text(BeautifulSoup(f"<p>{html}</p>", "lxml").find("p"))

    assert inline('visit our <a>Bug Report </a>forum.') == "visit our Bug Report forum."
    assert inline("<b>Bold </b>text") == "**Bold **text"
    assert inline("a<br>b") == "a\nb"
    assert inline("<span>士兵</span><span>：76</span>") == "士兵：76"


def test_inline_strong_emphasis_boundaries():
    """Synthetic <strong>/<b> cases for the ** marker encoding."""
    from bs4 import BeautifulSoup

    from ow2_patch.parse import _inline_text

    def inline(html):
        return _inline_text(BeautifulSoup(f"<p>{html}</p>", "lxml").find("p"))

    assert inline("x<strong>y</strong>z") == "x**y**z"
    assert inline("<strong>a<br>b</strong>") == "**a\nb**"
    assert inline("<strong><b>nested</b></strong>") == "**nested**"  # outer pair only
    assert inline("<b>x</b><b>y</b>") == "**x****y**"  # consecutive pairs
    assert inline("a ** literal") == "a ** literal"  # bare asterisks untouched
