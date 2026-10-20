"""Contract: the JSON artifacts consumed by external clients carry `schema_version`.

The local tool (`owpatch-tool`) reads `data/*_index.json` + `official_edits.json`
directly; without a version field it cannot tell an additive change from a
breaking one. Bumping `INDEX_SCHEMA_VERSION` is the only signal, so it must be
present in the committed artifacts too.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from ow2_patch.entries import build_official_edits
from ow2_patch.schema import INDEX_SCHEMA_VERSION

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
INDEXES = (
    "patches_index.json",
    "entries_index.json",
    "heroes_index.json",
    "official_edits.json",
)


def test_constant_is_positive_int():
    assert isinstance(INDEX_SCHEMA_VERSION, int)
    assert INDEX_SCHEMA_VERSION >= 1


@pytest.mark.parametrize("name", INDEXES)
def test_committed_index_has_schema_version(name):
    path = DATA / name
    if not path.exists():  # a fresh clone without data/ must not fail the suite
        pytest.skip(f"{name} not present in this checkout")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("schema_version") == INDEX_SCHEMA_VERSION


def test_official_edits_builder_sets_schema_version(tmp_path):
    record = {
        "ts": "2026-08-24T05:51:52Z",
        "kind": "modified",
        "patch_id": "en-2026-08-20-1",
        "site": "en",
        "date": "2026-08-20",
        "title": "t",
        "url": "https://example.com",
    }
    (tmp_path / "changelog.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    edits = build_official_edits(tmp_path)

    assert edits["schema_version"] == INDEX_SCHEMA_VERSION
    assert edits["updated"] == record["ts"]
    assert [e["ts"] for e in edits["edits"]["en-2026-08-20-1"]] == [record["ts"]]
