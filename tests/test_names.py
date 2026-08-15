"""Name resolution and slug tests."""

from __future__ import annotations

from ow2_patch.names import NameResolver, slugify


def test_slugify():
    assert slugify("Soldier: 76") == "soldier-76"
    assert slugify("Lúcio") == "lucio"
    assert slugify("D.Va") == "d-va"
    assert slugify("Wrecking Ball") == "wrecking-ball"
    assert slugify("Torbjörn") == "torbjorn"


def test_slugify_never_empty_for_cjk():
    # pure-CJK unknown hero names must not collapse to an empty slug
    slug = slugify("弗蕾娅")
    assert slug.startswith("hero-")
    assert slugify("弗蕾娅") == slug  # deterministic


def test_hero_en_lookup():
    r = NameResolver()
    slug, en, cn, role = r.hero("Soldier: 76", "en")
    assert (slug, en, cn, role) == ("soldier-76", "Soldier: 76", "士兵76", "damage")


def test_hero_cn_lookup():
    r = NameResolver()
    slug, en, cn, role = r.hero("卡西迪", "cn")
    assert (slug, en, cn, role) == ("cassidy", "Cassidy", "卡西迪", "damage")
    slug2, en2, cn2, _ = r.hero("金驭", "cn")
    assert (slug2, en2, cn2) == ("domina", "Domina", "金驭")


def test_hero_quoted_cn_name():
    # CN page renders some hero names with quotes: "飞天猫"
    r = NameResolver()
    slug, en, cn, _ = r.hero('"飞天猫"', "cn")
    assert (slug, en, cn) == ("jetpack-cat", "Jetpack Cat", "飞天猫")


def test_unknown_hero_auto_slug_and_warning():
    r = NameResolver()
    slug, en, cn, _ = r.hero("Some Brand New Hero", "en")
    assert slug == "some-brand-new-hero"
    assert en == "Some Brand New Hero"
    assert (en, "en") in r.unknown_heroes


def test_ability_lookup():
    r = NameResolver()
    slug, en, cn = r.ability("Heavy Pulse Rifle", "en")
    assert (slug, en, cn) == ("heavy-pulse-rifle", "Heavy Pulse Rifle", "重脉冲步枪")
    slug2, en2, cn2 = r.ability("重脉冲步枪", "cn")
    assert (slug2, en2, cn2) == ("heavy-pulse-rifle", "Heavy Pulse Rifle", "重脉冲步枪")


def test_unknown_ability_auto_slug():
    r = NameResolver()
    slug, en, cn = r.ability("Totally New Ability", "en")
    assert slug == "totally-new-ability"
    assert (en, "en") in r.unknown_abilities
