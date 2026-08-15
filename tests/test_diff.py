"""Change-detection tests: hashing, manifest comparison, deep diff."""

from __future__ import annotations

import pathlib

from ow2_patch.diff import ChangeEvent, deep_diff, detect_changes, patch_hash
from ow2_patch.model import AbilityUpdate, Change, HeroUpdate, Patch, Section
from ow2_patch.parse import parse_patch_notes

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def make_patch(damage: float = 65.0) -> Patch:
    return Patch(
        id="en-2026-08-12-1", site="en", date="2026-08-12", url="https://x", title="T",
        sections=[
            Section(
                type="hero_update", title="Tank", role="tank",
                heroes=[
                    HeroUpdate(
                        slug="d-mon", name_en="D.Mon",
                        abilities=[
                            AbilityUpdate(
                                name_en="Plasma Saber", slug="plasma-saber",
                                changes=[Change(text_en=f"Damage increased from 60 to {damage:.0f}.",
                                                before=60.0, after=damage, metric="damage")],
                            )
                        ],
                    )
                ],
            )
        ],
    )


def test_hash_stable_and_sensitive():
    a = make_patch()
    b = make_patch()
    assert patch_hash(a) == patch_hash(b)
    c = make_patch(damage=70.0)
    assert patch_hash(a) != patch_hash(c)


def test_detect_new_modified_unchanged():
    manifest = {make_patch().id: {"hash": patch_hash(make_patch())}}
    # new id
    fresh = make_patch()
    fresh.id = "en-2026-08-99-1"
    report = detect_changes([fresh], manifest)
    assert report.events == [ChangeEvent("new", fresh)]
    assert report.unchanged == 0

    # unchanged
    report = detect_changes([make_patch()], manifest)
    assert report.events == []
    assert report.unchanged == 1

    # modified
    report = detect_changes([make_patch(damage=70.0)], manifest)
    assert [e.kind for e in report.events] == ["modified"]


def test_deep_diff():
    old = make_patch()
    new = make_patch(damage=70.0)
    entries = deep_diff(patch_to_dict_plain(old), patch_to_dict_plain(new))
    after = next(e for e in entries if e.path.endswith("changes[0].after"))
    assert after.old == 65.0 and after.new == 70.0
    assert any(e.path.endswith("changes[0].text_en") for e in entries)
    assert deep_diff(patch_to_dict_plain(old), patch_to_dict_plain(old)) == []


def test_deep_diff_text_change():
    patches = parse_patch_notes(
        (FIXTURES / "en_2026_08.html").read_text(encoding="utf-8"), "en"
    )
    p = patches[0]
    patched = parse_patch_notes(
        (FIXTURES / "en_2026_08.html").read_text(encoding="utf-8"), "en"
    )[0]
    patched.sections[1].heroes[0].abilities[0].changes[0].after = 0.04
    entries = deep_diff(patch_to_dict_plain(p), patch_to_dict_plain(patched))
    assert any("after" in e.path for e in entries)


def patch_to_dict_plain(patch: Patch) -> dict:
    from ow2_patch.model import patch_to_dict

    return patch_to_dict(patch)
