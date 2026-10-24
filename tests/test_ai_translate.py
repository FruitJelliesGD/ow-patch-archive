"""Unit tests for the AI translation backfill helpers (no network)."""

from __future__ import annotations

import json
import pathlib

import pytest

from ow2_patch import ai_translate as ai

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _source(stem: str) -> dict:
    return json.loads((DATA / "patches" / "en" / f"{stem}.json").read_text(encoding="utf-8"))


def test_missing_patches_only_en_only_entries():
    refs = ai.missing_patches(DATA)
    assert all(ref.source_id.startswith("en-") for ref in refs)
    index = json.loads((DATA / "patches_index.json").read_text(encoding="utf-8"))
    paired = {p["patch_id_en"] for p in index["patches"] if p.get("patch_id_cn")}
    assert not any(ref.source_id in paired for ref in refs)


def test_flatten_and_build_preserve_skeletons():
    source = _source("2016-05-27-1")
    units = ai.flatten_patch(source)
    assert units
    translations = {
        unit.unit_id: ("- 测试译文" if unit.text.lstrip().startswith("- ") else "测试译文")
        for unit in units
    }
    out = ai.build_ai_patch(source, translations, model="test-model", provider="test")
    assert out["id"] == "ai-2016-05-27-1"
    assert out["site"] == "ai"
    assert out["source_patch_id"] == "en-2016-05-27-1"
    assert out["translation"]["source_hash"] == source["hash"]
    assert out["title"].startswith("《守望先锋》补丁说明——")
    assert len(out["sections"]) == len(source["sections"])
    assert ai.validate_ai_patch(source, out) == []


def test_flatten_covers_stadium_items():
    source = _source("2025-11-06-1")
    units = ai.flatten_patch(source)
    kinds = {unit.kind for unit in units}
    assert "item_line" in kinds
    assert "item_name" in kinds


def test_batches_do_not_split_units():
    units = [ai.Unit(f"u{i}", "change", "", "x" * 4000) for i in range(5)]
    batches = ai.make_batches(units, 6000)
    assert len(batches) == 5
    assert all(len(batch) == 1 for batch in batches)
    assert sum(len(batch) for batch in batches) == 5


def test_validate_rejects_empty_or_missing_translation():
    source = _source("2016-05-27-1")
    units = ai.flatten_patch(source)
    translations = {unit.unit_id: "测试译文" for unit in units}
    out = ai.build_ai_patch(source, translations, model="test", provider="test")
    first = out["sections"][0]
    first["title"] = ""
    errors = ai.validate_ai_patch(source, out)
    assert any("不是中文或为空" in error for error in errors)


def test_parse_translation_json_handles_fences_and_multiple_objects():
    assert ai.parse_translation_json('```json\n{"a": "甲"}\n```') == {"a": "甲"}
    assert ai.parse_translation_json('{"a": "甲"}\n{"b": "乙"}') == {"a": "甲", "b": "乙"}
    with pytest.raises(ai.TranslateError):
        ai.parse_translation_json("没有 JSON")


def test_credentials_from_explicit_config_and_public_mask(tmp_path, monkeypatch):
    monkeypatch.delenv("OWPATCH_API_KEY", raising=False)
    monkeypatch.delenv("OWPATCH_API_BASE", raising=False)
    monkeypatch.delenv("OWPATCH_API_MODEL", raising=False)
    config = tmp_path / "ui-config.toml"
    config.write_text(
        '[translate]\napi_key = "unit-test-key"\nbase_url = "https://example.test"\nmodel = "unit-model"\n',
        encoding="utf-8",
    )
    settings = ai.load_api_settings(translate_config=str(config))
    assert settings.api_key == "unit-test-key"
    assert settings.base_url == "https://example.test"
    assert settings.model == "unit-model"
    assert settings.public()["api_key_set"] is True
    assert "unit-test-key" not in json.dumps(settings.public())


def test_rebuild_index_from_files(tmp_path):
    ai_dir = tmp_path / "ai_translations" / "zh" / "2016"
    ai_dir.mkdir(parents=True)
    (ai_dir / "2016-01-01-1.json").write_text(
        json.dumps(
            {
                "id": "ai-2016-01-01-1",
                "site": "ai",
                "source_patch_id": "en-2016-01-01-1",
                "date": "2016-01-01",
                "title": "《守望先锋》补丁说明——2016年1月1日",
                "translation": {"status": "draft"},
                "sections": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    index = ai.rebuild_index(tmp_path)
    assert len(index["translations"]) == 1
    assert index["translations"][0]["file"] == "zh/2016/2016-01-01-1.json"
    assert index["schema_version"] == 1


def test_status_reports_no_raw_key(monkeypatch):
    monkeypatch.setattr(ai, "load_api_settings", lambda **_: ai.ApiSettings("secret-value", "https://x", "m", "test"))
    info = ai.status(DATA, year="2016")
    assert info["missing"] >= 0
    assert "secret-value" not in json.dumps(info)


def test_main_defaults_to_cwd_data(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert ai.main(["status", "--json"]) == 0


def test_workflows_wire_ai_translation():
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "ai-translate" in pages
    workflow = (ROOT / ".github" / "workflows" / "ai-translate.yml").read_text(encoding="utf-8")
    assert "OWPATCH_API_KEY" in workflow
    assert "tools/ai_translate.py run" in workflow
    assert "git add data/ai_translations" in workflow
