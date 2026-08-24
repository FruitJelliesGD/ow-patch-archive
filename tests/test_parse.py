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


def test_legacy_2016_parses_structurally():
    """OW1-era pages (no PatchNotes-section divs) parse into sections instead
    of degrading to a raw_text blob."""
    patches = load("en_2016_05.html", "en")
    assert len(patches) == 1
    p = patches[0]
    assert p.date == "2016-05-27"
    assert p.raw_text is None
    assert [s.title for s in p.sections] == ["GENERAL:"]
    sec = p.sections[0]
    assert sec.type == "generic_update"
    assert "ForceFMA" in sec.description


def test_legacy_2016_07_heroes_parse_structurally():
    """A hero-bearing legacy patch yields hero blocks with abilities, general
    lines and dev notes — the same shape modern patches have."""
    patches = load("en_2016_07_19.html", "en")
    p = patches[0]
    assert p.raw_text is None
    sec = next(s for s in p.sections if s.type == "hero_update")
    assert sec.title == "HERO BALANCE UPDATES"
    by_name = {h.name_en: h for h in sec.heroes}
    assert set(by_name) >= {"Bastion", "D.Va", "McCree", "Zenyatta"}

    dva = by_name["D.Va"]
    assert [a.name_en for a in dva.abilities] == ["Defense Matrix", "Self-Destruct"]
    dm = dva.abilities[0]
    assert len(dm.changes) == 7  # sub-heading names drop, real lines survive
    assert dm.changes[0].text_en == "Cooldown decreased from 10 seconds to 1 second"
    # li lines that carry their own nested detail must not be lost
    assert any("A new resource meter has been added" in c.text_en for c in dm.changes)
    assert any("reclassified as an alternate fire" in c.text_en for c in dm.changes)
    assert dva.dev_note and dva.dev_note.startswith("D.Va isn't being selected")

    zen = by_name["Zenyatta"]
    assert any("Base shields increased by 50" in g for g in zen.general)
    assert [a.name_en for a in zen.abilities] == ["Orb of Discord and Orb of Harmony", "Transcendence"]

    mccree = by_name["McCree"]
    assert mccree.dev_note and "range" in mccree.dev_note

    # PATCH FEATURES "New Hero: Ana" becomes a generic block with its intro
    feat = next(s for s in p.sections if s.title == "PATCH FEATURES")
    assert feat.blocks[0].title == "New Hero: Ana (Support)"
    assert "After being out of the fight" in feat.blocks[0].body


def test_legacy_2019_plain_p_abilities():
    """2019-era pages name abilities in plain <p> before their <ul>."""
    patches = load("en_2019_10_15.html", "en")
    p = patches[0]
    sec = next(s for s in p.sections if s.type == "hero_update")
    d = next(h for h in sec.heroes if h.name_en == "D.Va")
    assert [a.name_en for a in d.abilities] == ["Defense Matrix"]
    assert len(d.abilities[0].changes) == 2
    assert d.dev_note and d.dev_note.startswith("This change will allow D.Va")


def test_legacy_2016_06_bare_b_hero_markers():
    """June 2016 pages mark heroes with bare <b><a>…</a></b> elements."""
    patches = load("en_2016_06_14.html", "en")
    p = patches[0]
    sec = next(s for s in p.sections if s.type == "hero_update")
    by_name = {h.name_en: h for h in sec.heroes}
    assert set(by_name) >= {"McCree", "Widowmaker"}
    mccree = by_name["McCree"]
    assert [a.name_en for a in mccree.abilities] == ["Peacekeeper"]
    # deep-nested change lines with their own sub-detail survive
    pk = mccree.abilities[0].changes
    assert any("Recovery time" in c.text_en for c in pk)
    assert any("Bullet damage decreased from 70 to 45" in c.text_en for c in pk)
    assert mccree.dev_note and "performing too well" in mccree.dev_note


def test_legacy_block_p_ul_interleaving():
    """Interleaved <p> paragraphs and <ul> lists inside one block must all
    survive (a later <p> must not clobber earlier list lines)."""
    patches = load("en_2019_10_24.html", "en")
    p = patches[0]
    rewards = next(b for s in p.sections for b in s.blocks
                   if b.title and "Warcraft" in b.title)
    assert "a flurry of new rewards" in rewards.body
    assert "- " in rewards.body  # list lines still present after later <p>s
    assert "animated sprays" in rewards.body


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


def test_inline_links_and_images_encoded():
    """<a href> becomes [text](url) and <img> ![alt](src) — https only; the
    _text chain stays flat (links/banners are rich-text-only)."""
    from bs4 import BeautifulSoup

    from ow2_patch.parse import _inline_text, _text

    def inline(html):
        return _inline_text(BeautifulSoup(f"<p>{html}</p>", "lxml").find("p"))

    assert inline('see <a href="https://ow.blizzard.cn/news/">here</a>!') == "see [here](https://ow.blizzard.cn/news/)!"
    assert inline('see <a href="http://x.example/">plain</a>') == "see [plain](http://x.example/)"
    assert inline('<a href="javascript:alert(1)">x</a>') == "x"  # non-http href stays text
    assert inline('<a>no href</a>') == "no href"
    assert inline('<img src="https://cdn.example/a.jpg" alt="banner">') == "![banner](https://cdn.example/a.jpg)"
    assert inline('<img src="data:image/png;base64,AAAA">') == ""  # non-https skipped
    assert inline('<a href="https://x"><strong>b</strong></a>') == "[**b**](https://x)"
    p = BeautifulSoup('<p>see <a href="https://x">here</a></p>', "lxml").find("p")
    assert _text(p) == "see here"  # flat text chain keeps the label, no syntax


def test_en_map_update_sections():
    """EN map sections: type map_update, before/after image pairs with the
    area name carried forward across empty-name entries; no flattened
    description text."""
    patches = load("en_2026_08_11.html", "en")
    maps_secs = [s for s in patches[0].sections if s.type == "map_update"]
    assert [s.title for s in maps_secs] == ["Busan - Control", "Eichenwalde - Hybrid", "Paraíso - Hybrid"]
    busan = maps_secs[0]
    assert busan.description is None  # the flattening fallback is gated off
    assert len(busan.maps) == 6
    first = busan.maps[0]
    assert first.map_name is None and first.area == "Downtown"
    assert first.before.startswith("https://images.blz-contentstack.com") and ".Before." in first.before
    assert first.after.startswith("https://") and ".After." in first.after
    # empty-name sliders carry the previous name forward (Downtown.02 etc.)
    assert busan.maps[1].area == "Downtown"


def test_en_section_dev_captured():
    patches = load("en_2026_08_11.html", "en")
    hero_updates = next(s for s in patches[0].sections if s.title == "Hero Updates")
    assert hero_updates.dev and hero_updates.dev.startswith("Several underutilized perks")


def test_en_stadium_items_structured():
    patches = load("en_2026_08_11.html", "en")
    dva = next(h for s in patches[0].sections for h in s.heroes if h.name_en == "D.Va")
    items = {i.name_en: i for i in dva.stadium_items}
    assert len(dva.stadium_items) >= 10
    facet = items["Facetanking"]
    assert facet.kind == "power" and facet.rarity is None and facet.status == "reworked"
    assert facet.raw_text == ["Facetanking - Power"]
    assert "Reworked from" in facet.lines_en[0]
    # rarity-bearing items live on other Stadium heroes (Core Cooling -> Orisa)
    orisa = next(h for s in patches[0].sections for h in s.heroes
                 if h.name_en == "Orisa" and any(i.name_en == "Core Cooling" for i in h.stadium_items))
    core = next(i for i in orisa.stadium_items if i.name_en == "Core Cooling")
    assert core.kind == "weapon" and core.rarity == "Epic" and core.status == "reworked"
    assert core.raw_text == ["Core Cooling - Epic Weapon Hero Item"]
    bingo = next(i for s in patches[0].sections for h in s.heroes
                 for i in h.stadium_items if i.name_en == "Bingo")
    assert bingo.rarity == "Epic" and bingo.status == "added" and bingo.lines_en[0] == "New"
    # the marker lines no longer leak into flat general lines
    assert not any("Hero Item" in g for g in dva.general)


def test_cn_map_block_extraction():
    """CN map updates live inside the 地图更新 generic block as a title/img
    sequence; the parser extracts them to section.maps and empties the body."""
    patches = load("cn_2026_08_12.html", "cn")
    sec = next(s for s in patches[0].sections if s.title == "核心游戏模式更新")
    assert len(sec.maps) == 18
    first = sec.maps[0]
    assert first.map_name == "釜山——占领要点" and first.area == "城区"
    assert first.before.startswith("https://ld5.res.netease.com") and first.after.startswith("https://ld5.res.netease.com")
    # map block body cleared so the flattened text does not duplicate the images
    map_block = next(b for b in sec.blocks if b.title == "地图更新")
    assert not map_block.body
    areas = {m.area for m in sec.maps}
    assert "A点" in areas and "B点" in areas


def test_cn_stadium_items_structured():
    patches = load("cn_2026_08_12.html", "cn")
    dva = next(h for s in patches[0].sections for h in s.heroes if h.name_cn == "D.Va")
    items = {i.name_cn: i for i in dva.stadium_items}
    assert items["脸接伤害"].kind == "power" and items["脸接伤害"].status == "moved"
    orisa = next(h for s in patches[0].sections for h in s.heroes
                 if h.name_cn == "奥丽莎" and any(i.name_cn == "核心冷却" for i in h.stadium_items))
    core = next(i for i in orisa.stadium_items if i.name_cn == "核心冷却")
    assert core.rarity == "史诗" and core.kind == "weapon" and core.status == "moved"
    assert core.raw_text == ["核心冷却——史诗武器英雄物品"]
    assert not any("英雄物品" in g for g in dva.general)


# ---------- Contentstack-format CN patches ----------

def test_cn_contentstack_synthetic():
    """The Contentstack raw format (no PatchNotes-patch/section wrappers):
    title + sections with generic updates and hero blocks map to the model."""
    patches = load("cn_contentstack_synthetic.html", "cn")
    assert [p.id for p in patches] == ["cn-2026-02-11-1"]
    p = patches[0]
    assert p.date == "2026-02-11"
    assert p.title == "《守望先锋》补丁说明——2026年2月11日"
    assert [s.type for s in p.sections] == ["generic_update", "hero_update"]

    gen = p.sections[0]
    assert gen.title == "综合更新"
    assert "新界面新体验" in gen.description
    block = gen.blocks[0]
    assert block.title == "补给更新"
    assert "第15至20赛季" in block.body
    assert "区块开发注" in block.dev

    hero_sec = p.sections[1]
    assert hero_sec.role == "tank"
    orisa, zhanchou = hero_sec.heroes
    assert orisa.name_cn == "奥丽莎" and orisa.role == "tank"
    # （6v6）perk suffix is stripped; perks structured, plain p+ul → general
    assert [pk.name_cn for pk in orisa.perks] == ["防护屏障", "充能标枪", "屏障投掷"]
    assert orisa.perks[0].lines_cn == ["冷却时间从8秒延长至10秒。"]
    assert orisa.perks[2].status == "removed"  # 已移除。 full-width period stripped
    assert "基础生命值从375降低至325。" in orisa.general
    assert "总生命值从700降低至650。" in orisa.general
    assert "降低护盾以提升对抗性。" in orisa.dev_note
    # （全新）hero-name suffix stripped; ——异能 item marker → stadium item
    assert zhanchou.name_cn == "斩仇"
    assert len(zhanchou.stadium_items) == 1
    assert zhanchou.stadium_items[0].name_cn == "巨力劈斩"


def test_cn_contentstack_section9_real():
    """Real Feb-11 content (title + section 9 重装, d-va + mauga): hero general
    lines and the 动力弹带 perk parse like the normal CN format."""
    patches = load("cn_contentstack_section9.html", "cn")
    assert len(patches) == 1
    sec = patches[0].sections[0]
    assert sec.title == "重装" and sec.role == "tank"
    dva, mauga = sec.heroes
    assert dva.name_cn == "D.Va"
    assert "基础生命值从375降低至325。（5v5）" in dva.general
    assert "总生命值从700降低至650。" in dva.general
    assert "削减基础生命值可以让对手更容易摧毁她的机甲。" in dva.dev_note
    assert mauga.name_cn == "毛加"
    assert [pk.name_cn for pk in mauga.perks] == ["动力弹带"]


def test_cn_2026_02_full_month():
    """Regression over the real Feb-2026 month page: the 3 normal patches parse
    unchanged and the Contentstack 02-11 patch joins as the 4th."""
    patches = load("cn_2026_02.html", "cn")
    assert [p.id for p in patches] == [
        "cn-2026-02-25-1", "cn-2026-02-19-1", "cn-2026-02-14-1", "cn-2026-02-11-1"]
    p = patches[-1]
    assert p.title == "《守望先锋》补丁说明——2026年2月11日"
    assert len(p.sections) == 22
    tank = next(s for s in p.sections if s.title == "重装")
    damage = next(s for s in p.sections if s.title == "输出")
    support = next(s for s in p.sections if s.title == "支援")
    assert len(tank.heroes) == 9
    assert len(damage.heroes) == 14
    assert len(support.heroes) == 8
    # the 3 normal patches are untouched by the trailing contentstack block
    assert patches[0].title == "《守望先锋》补丁说明——2026年2月25日"
    assert patches[1].title == "《守望先锋》补丁说明——2026年2月19日"
    assert all(s.type == "generic_update" for s in patches[0].sections)


def test_cn_hybrid_contentstack_title_with_classic_block():
    """CN hybrid format (Contentstack title div + classic block without a
    .PatchNotes-patchTitle): the block's sections must be grafted onto the
    title-only Contentstack patch instead of being silently dropped."""
    patches = load("cn_hybrid_title_block.html", "cn")
    assert [p.id for p in patches] == ["cn-2025-07-23-1", "cn-2025-07-25-1"]
    p = patches[1]
    assert p.date == "2025-07-25"
    assert p.title == "《守望先锋》补丁说明——2025年7月25日"
    assert p.raw_text is None
    assert [s.title for s in p.sections] == ["平衡性在线修正更新", "角斗领域更新", "重装"]
    assert p.sections[0].type == "generic_update"
    assert "回放代码仍然可用" in p.sections[0].description

    hero = p.sections[2].heroes[0]
    assert hero.name_cn == "D.Va" and hero.role == "tank"
    assert hero.dev_note and "微型飞弹" in hero.dev_note
    item = hero.stadium_items[0]
    assert item.name_cn == "反制措施" and item.kind == "power"
    assert item.lines_cn == ["要求抵挡的伤害从100提高到150。"]


def test_cn_contentstack_title_only_degrades_to_raw_text():
    """A Contentstack group with a title but no recognized section keys must
    degrade to raw_text (content never lost) instead of an empty stub."""
    html = ('<div contentstack-field-context="text" contentstack-unique-entry-key="title">'
            '《守望先锋》补丁说明——2025年7月25日</div>'
            '<div contentstack-field-context="text" '
            'contentstack-unique-entry-key="sections[0].mystery_field">'
            '尚未支持的键内容</div>')
    patches = parse_patch_notes(html, "cn", url="https://example/x")
    assert len(patches) == 1
    p = patches[0]
    assert p.id == "cn-2025-07-25-1"
    assert p.sections == []
    assert p.raw_text and "尚未支持的键内容" in p.raw_text


def test_en_perk_6v6_suffix():
    """EN perk markers tolerate the (5v5)/(6v6) suffix — 'Protective Barrier –
    Major Perk (6v6)' must parse as a perk, keeping EN/CN perk counts aligned
    (the mis-alignment caused an ability_map name flip for Orisa)."""
    patches = load("en_perk_6v6.html", "en")
    orisa = patches[0].sections[0].heroes[0]
    assert [pk.name_en for pk in orisa.perks] == ["Protective Barrier", "Charged Javelin"]
    assert orisa.perks[0].lines_en == ["Cooldown increased from 8 to 10 seconds."]
    assert "Protective Barrier" not in orisa.general
