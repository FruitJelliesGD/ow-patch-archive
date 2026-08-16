"""Hash neutrality tests: derived fields / attribution moves never change the hash."""

from __future__ import annotations

import json
import pathlib

from ow2_patch.diff import (
    HASH_SCHEMA_VERSION,
    ensure_hash_schema,
    patch_hash,
    patch_hash_from_dict,
)
from ow2_patch.model import AbilityUpdate, Change, HeroUpdate, Patch, Section
from ow2_patch.parse import parse_patch_notes

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def base_patch() -> Patch:
    return Patch(
        id="en-2026-08-12-1", site="en", date="2026-08-12", url="https://x", title="T", seq=1,
        sections=[
            Section(type="hero_update", title="Tank", role="tank",
                    heroes=[HeroUpdate(
                        slug="d-mon", name_en="D.Mon",
                        general=["Fixed a bug."],
                        abilities=[AbilityUpdate(
                            name_en="Plasma Saber", slug="plasma-saber",
                            changes=[Change(text_en="Damage increased from 60 to 65.",
                                            before=60.0, after=65.0, metric="damage")],
                        )],
                    )]),
        ],
    )


def test_hash_ignores_derived_fields():
    base = patch_hash(base_patch())
    derived = base_patch()
    derived.sections[0].heroes[0].abilities[0].changes[0].after = 70.0
    derived.sections[0].heroes[0].abilities[0].changes[0].by = 10.0
    derived.sections[0].heroes[0].abilities[0].changes[0].metric = "damage"
    derived.sections[0].heroes[0].slug = "renamed-slug"
    assert patch_hash(derived) == base


def test_hash_ignores_attribution_move():
    # general entry moved into the ability's changes -> same text bag -> same hash
    patch = base_patch()
    hero = patch.sections[0].heroes[0]
    hero.general.append("Self healing penalty increased from 25% to 40%.")
    h1 = patch_hash(patch)

    moved = base_patch()
    mhero = moved.sections[0].heroes[0]
    mhero.abilities[0].changes.append(
        Change(text_en="Self healing penalty increased from 25% to 40%.")
    )
    assert patch_hash(moved) == h1


def test_hash_changes_when_text_changes():
    base = patch_hash(base_patch())
    edited = base_patch()
    edited.sections[0].heroes[0].abilities[0].changes[0].text_en = "Damage increased from 60 to 70."
    assert patch_hash(edited) != base


def test_migration_idempotent(tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "patches" / "en").mkdir(parents=True)
    patch = parse_patch_notes(
        (FIXTURES / "en_2026_08.html").read_text(encoding="utf-8"), "en", url="https://x"
    )[0]
    from ow2_patch.model import patch_to_dict

    data = patch_to_dict(patch)
    data["hash"] = "sha256:old"
    patch_file = data_dir / "patches" / "en" / "2026-08-14-1.json"
    patch_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    manifest = {patch.id: {"hash": "sha256:old", "site": "en", "date": "2026-08-14"}}

    assert ensure_hash_schema(data_dir, manifest) is True
    assert manifest["hash_schema"] == HASH_SCHEMA_VERSION
    new_hash = json.loads(patch_file.read_text(encoding="utf-8"))["hash"]
    assert new_hash.startswith("sha256:")
    assert manifest[patch.id]["hash"] == new_hash

    # second run is a no-op and byte-identical
    before = patch_file.read_bytes()
    assert ensure_hash_schema(data_dir, manifest) is False
    assert patch_file.read_bytes() == before

    # dict-based and object-based hashes agree on the migrated data
    assert patch_hash_from_dict(json.loads(patch_file.read_text(encoding="utf-8"))) == new_hash
