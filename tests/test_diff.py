"""Change-detection tests: hashing, manifest comparison, deep diff."""

from __future__ import annotations

import pathlib

from ow2_patch.diff import ChangeEvent, clean_legacy_text, deep_diff, detect_changes, patch_hash
from ow2_patch.model import AbilityUpdate, Change, HeroUpdate, Patch, Section
from ow2_patch.parse import parse_patch_notes

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

# Legacy (OW1-era) raw_text as archived on 2026-08-16 (site chrome included)
# vs the same patch re-fetched on 2026-08-17 (chrome structurally stripped).
_CHROME_OLD = (
    "May 27, 2016 Overwatch Patch Notes – May 26, 2016 A new patch is now live. "
    "Read below to learn about the latest changes. To share your feedback, please post in the "
    "General Discussion forum. For a list of known issues, visit our Bug Report forum. For "
    "troubleshooting assistance, visit our Technical Support forum. Please note that some changes "
    "may not be documented or described in full detail. GENERAL: Added a new \"ForceFMA\" "
    "configuration option which can be set by users working with our support teams to mitigate a "
    "specific audio crash Top of post June Patch Notes June Live Patch Notes These patch notes "
    "represent general changes made to the Live version of Overwatch and the balance changes listed "
    "affect Quick Play, Competitive Play, Arcade, and Custom Games. General Discussion forum Bug "
    "Report forum Technical Support forum"
)
_CHROME_MULTI_OLD = (
    "June 14, 2016 Overwatch Patch Notes – June 14, 2016 A new patch is now live on Windows PC. "
    "Read below to learn about the latest changes. To share your feedback, please post in the "
    "General Discussion forum. For a list of known issues, visit our Bug Report forum. For "
    "troubleshooting assistance, visit our Technical Support forum. HERO BALANCE CHANGES McCree "
    "Peacekeeper Alternate Fire Recovery time decreased from 0.75 seconds to 0.3 seconds Top of "
    "post July Patch Notes July May Patch Notes May Live Patch Notes These patch notes represent "
    "general changes made to the Live version of Overwatch and the balance changes listed affect "
    "Quick Play, Competitive Play, Arcade, and Custom Games. General Discussion forum Bug Report "
    "forum Technical Support forum"
)


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


def _legacy_patch(raw_text: str) -> Patch:
    return Patch(id="en-2016-05-27-1", site="en", date="2016-05-27", url="https://x",
                 title="Overwatch Patch Notes – May 26, 2016", seq=1, raw_text=raw_text)


def test_clean_legacy_text_chrome_variants():
    """Chrome variants of the same legacy patch must clean to the same content."""
    stripped = _CHROME_OLD.replace(" Top of post June Patch Notes June ", " ")
    multi_stripped = _CHROME_MULTI_OLD.replace(
        " Top of post July Patch Notes July May Patch Notes May ", " ")
    assert clean_legacy_text(_CHROME_OLD) == clean_legacy_text(stripped)
    assert clean_legacy_text(_CHROME_MULTI_OLD) == clean_legacy_text(multi_stripped)
    cleaned = clean_legacy_text(_CHROME_OLD)
    assert "ForceFMA" in cleaned and "McCree" in clean_legacy_text(_CHROME_MULTI_OLD)
    for chrome in ("Top of post", "June Patch Notes", "Live Patch Notes",
                   "General Discussion forum", "These patch notes represent"):
        assert chrome not in cleaned
    # the patch title itself is content and must survive cleaning
    assert "Overwatch Patch Notes – May 26, 2016" in cleaned


def test_patch_hash_ignores_legacy_chrome():
    """Legacy-patch hashes are immune to site template chrome churn."""
    base = _legacy_patch(_CHROME_OLD)
    stripped = _legacy_patch(_CHROME_OLD.replace(" Top of post June Patch Notes June ", " "))
    assert patch_hash(base) == patch_hash(stripped)
    edited = _legacy_patch(_CHROME_OLD.replace("ForceFMA", "ForceFMA2"))
    assert patch_hash(base) != patch_hash(edited)


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
