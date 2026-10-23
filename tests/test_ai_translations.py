"""Contract tests for the optional AI-translation overlay.

The overlay lives entirely outside the official pipeline: `data/ai_translations/`
holds an index plus localized patch JSON, and the site reads it only when the
reader asks for `?lang=ai`. These tests pin the contract that matters:

- the three trial patches exist and are registered in the index;
- the localized JSON mirrors the English source structure exactly (sections,
  heroes, abilities, changes, blocks, maps) and preserves every numeric field;
- every source sentence has a Chinese counterpart (`text_en` is null, `text_cn`
  is non-empty), while slugs/names/icons and extracted numbers stay untouched;
- nothing leaks into the official indexes, hero timelines or entries.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
AI_DIR = DATA / "ai_translations"
REQUIRED = {
    "en-2016-06-14-1": "2016-06-14",
    "en-2016-09-02-1": "2016-09-02",
    "en-2016-12-13-1": "2016-12-13",
}
PLACEHOLDERS = ("[待补充]", "TODO", "（译注）", "(译注)")
# Labels that are intentionally identical in the English source and Chinese
# translation (UI/AI/platform markers); they must not trip the CJK check.
EN_ONLY_OK = {"AI", "A.I.", "UI", "PC", "PS4 Pro", "Console", "4K", "Boop", "PvP HUD"}
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?|\.\d+")
LONG_EN_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9'’.:-]*(?:\s+[A-Za-z][A-Za-z0-9'’.:-]*){6,}"
)


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_id(source_id: str) -> pathlib.Path:
    match = re.fullmatch(r"en-(\d{4}-\d{2}-\d{2})-(\d+)", source_id)
    assert match, f"unexpected source id: {source_id}"
    return DATA / "patches" / "en" / f"{match.group(1)}-{match.group(2)}.json"


def _is_zh(text: str | None) -> bool:
    return bool(text) and bool(CJK_RE.search(text))


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("text_cn") or value.get("text_en") or ""
    return str(value)


def _source_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("text_en") or value.get("text_cn") or ""
    return str(value)


def _bullet_shape(text: str) -> list[int]:
    """Indent widths of bullet lines; translation must not merge/split them."""
    return [
        len(line) - len(line.lstrip(" "))
        for line in text.splitlines()
        if line.lstrip().startswith("- ")
    ]


def _numbers(text: str) -> Counter:
    # `.5` and `0.5` are the same value: normalize the leading-dot form so a
    # translation may use the conventional Chinese spelling without failing.
    tokens = [(t if not t.startswith(".") else "0" + t) for t in NUMBER_RE.findall(text)]
    return Counter(tokens)


def _nonempty_lines(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def _assert_localized(
    source: str,
    target: str,
    where: str,
    *,
    strict_numbers: bool = False,
    allow_english_equal: bool = False,
    allow_english: bool = False,
) -> None:
    if not source:
        return
    same_english = allow_english_equal and target.strip() == source.strip()
    if not allow_english and not same_english and not _is_zh(target) and target.strip() not in EN_ONLY_OK:
        raise AssertionError(f"{where}: target is not Chinese: {target!r}")
    if strict_numbers and _numbers(source) != _numbers(target):
        raise AssertionError(
            f"{where}: number tokens changed\nsource={_numbers(source)}\ntarget={_numbers(target)}"
        )
    if _bullet_shape(source) != _bullet_shape(target):
        raise AssertionError(
            f"{where}: bullet structure changed\nsource={_bullet_shape(source)}\ntarget={_bullet_shape(target)}"
        )
    for marker in PLACEHOLDERS:
        assert marker not in target, f"{where}: placeholder {marker}"
    long_en = LONG_EN_RE.search(target)
    if long_en and not allow_english:
        raise AssertionError(f"{where}: untranslated English sentence {long_en.group(0)!r}")


def _compare_change(src: dict, out: dict, where: str) -> None:
    for key in ("before", "after", "by", "by_pct", "metric", "raw_metric", "unit"):
        assert out.get(key) == src.get(key), f"{where}: numeric field {key} changed"
    assert out.get("text_en") is None, f"{where}: text_en must be null"
    strict = any(src.get(key) is not None for key in ("before", "after", "by", "by_pct"))
    _assert_localized(_text(src.get("text_en")), _text(out.get("text_cn")), where, strict_numbers=strict)


def _compare_block(src: dict, out: dict, where: str) -> None:
    if src.get("title"):
        assert out.get("title") is not None, f"{where}: block title missing"
        _assert_localized(src["title"], out["title"], f"{where}.title", allow_english_equal=True)
    if src.get("body"):
        assert out.get("body"), f"{where}: block body missing"
        _assert_localized(src["body"], out["body"], f"{where}.body", allow_english=True)
    if src.get("dev"):
        assert out.get("dev"), f"{where}: block dev missing"
        _assert_localized(src["dev"], out["dev"], f"{where}.dev")


def _compare_hero(src: dict, out: dict, where: str) -> None:
    for key in ("slug", "name_en", "role", "icon"):
        assert out.get(key) == src.get(key), f"{where}: hero field {key} changed"
    assert out.get("name_cn"), f"{where}: hero name_cn missing"
    if src.get("name_cn"):
        assert out["name_cn"] == src["name_cn"], f"{where}: existing hero name_cn changed"
    if src.get("dev_note"):
        assert out.get("dev_note"), f"{where}: hero dev_note missing"
        _assert_localized(src["dev_note"], out["dev_note"], f"{where}.dev_note")
    general_src = src.get("general") or []
    general_out = out.get("general") or []
    assert len(general_out) == len(general_src), f"{where}: general count changed"
    for i, (a, b) in enumerate(zip(general_src, general_out)):
        strict = isinstance(a, dict) and any(a.get(key) is not None for key in ("before", "after", "by", "by_pct"))
        _assert_localized(_source_text(a), _text(b), f"{where}.general[{i}]", strict_numbers=strict)
        if isinstance(a, dict):
            assert b.get("text_en") is None, f"{where}.general[{i}]: text_en must be null"
            for key in ("subject", "dimension", "before", "after", "by", "by_pct", "metric", "unit"):
                assert b.get(key) == a.get(key), f"{where}.general[{i}]: field {key} changed"
    for pi, (p, po) in enumerate(zip(src.get("perks") or [], out.get("perks") or [])):
        assert p.get("name_en") == po.get("name_en"), f"{where}.perk[{pi}]: name_en changed"
        assert p.get("status") == po.get("status"), f"{where}.perk[{pi}]: status changed"
        assert po.get("name_cn"), f"{where}.perk[{pi}]: name_cn missing"
        for li, (line, out_line) in enumerate(zip(p.get("lines_en") or [], po.get("lines_cn") or [])):
            _assert_localized(line, out_line, f"{where}.perk[{pi}].lines[{li}]")
    assert len(src.get("perks") or []) == len(out.get("perks") or []), f"{where}: perk count changed"
    for ii, (item, io) in enumerate(zip(src.get("stadium_items") or [], out.get("stadium_items") or [])):
        for key in ("status", "kind", "rarity"):
            assert item.get(key) == io.get(key), f"{where}.item[{ii}]: {key} changed"
        assert io.get("name_cn"), f"{where}.item[{ii}]: name_cn missing"
        for li, (line, out_line) in enumerate(zip(item.get("lines_en") or [], io.get("lines_cn") or [])):
            _assert_localized(line, out_line, f"{where}.item[{ii}].lines[{li}]")
    assert len(src.get("stadium_items") or []) == len(out.get("stadium_items") or []), f"{where}: stadium count changed"
    abilities_src = src.get("abilities") or []
    abilities_out = out.get("abilities") or []
    assert len(abilities_out) == len(abilities_src), f"{where}: ability count changed"
    for ai, (a, b) in enumerate(zip(abilities_src, abilities_out)):
        aw = f"{where}.abilities[{ai}]"
        for key in ("slug", "name_en", "icon"):
            assert b.get(key) == a.get(key), f"{aw}: ability field {key} changed"
        if a.get("name_en") or a.get("name_cn") or a.get("slug"):
            assert b.get("name_cn"), f"{aw}: ability name_cn missing"
        if a.get("name_cn"):
            assert b["name_cn"] == a["name_cn"], f"{aw}: existing ability name_cn changed"
        changes_src = a.get("changes") or []
        changes_out = b.get("changes") or []
        assert len(changes_out) == len(changes_src), f"{aw}: change count changed"
        for ci, (c, d) in enumerate(zip(changes_src, changes_out)):
            _compare_change(c, d, f"{aw}.changes[{ci}]")


def _compare_patch(src: dict, out: dict) -> None:
    assert out["site"] == "ai"
    assert out["id"] == f"ai-{src['date']}-{src['seq']}"
    assert out["source_patch_id"] == src["id"]
    assert out["date"] == src["date"] and out["seq"] == src["seq"]
    assert out["url"] == src["url"]
    assert out["title"].startswith("《守望先锋》补丁说明——")
    assert out["translation"]["source_hash"] == src["hash"]
    assert out["translation"]["status"] == "draft"
    sections_src = src.get("sections") or []
    sections_out = out.get("sections") or []
    assert len(sections_out) == len(sections_src), "section count changed"
    for si, (a, b) in enumerate(zip(sections_src, sections_out)):
        sw = f"sections[{si}]"
        assert b.get("type") == a.get("type"), f"{sw}: type changed"
        assert b.get("role") == a.get("role"), f"{sw}: role changed"
        assert (b.get("title") is None) == (a.get("title") is None), f"{sw}: title nullability changed"
        if a.get("title"):
            _assert_localized(_source_text(a.get("title")), _text(b.get("title")), f"{sw}.title", allow_english_equal=True)
        if a.get("description"):
            _assert_localized(a["description"], b.get("description", ""), f"{sw}.description")
        if a.get("dev"):
            _assert_localized(a["dev"], b.get("dev", ""), f"{sw}.dev")
        heroes_src = a.get("heroes") or []
        heroes_out = b.get("heroes") or []
        assert len(heroes_out) == len(heroes_src), f"{sw}: hero count changed"
        for hi, (h, i) in enumerate(zip(heroes_src, heroes_out)):
            _compare_hero(h, i, f"{sw}.heroes[{hi}]")
        blocks_src = a.get("blocks") or []
        blocks_out = b.get("blocks") or []
        assert len(blocks_out) == len(blocks_src), f"{sw}: block count changed"
        for bi, (bl, bo) in enumerate(zip(blocks_src, blocks_out)):
            _compare_block(bl, bo, f"{sw}.blocks[{bi}]")
        maps_src = a.get("maps") or []
        maps_out = b.get("maps") or []
        assert len(maps_out) == len(maps_src), f"{sw}: map count changed"


def _ai_files() -> dict[str, dict]:
    index = _load(AI_DIR / "index.json")
    assert index.get("schema_version") == 1
    assert "非官方" in index.get("notice", "")
    entries = {e["source_patch_id"]: e for e in index.get("translations", [])}
    assert set(REQUIRED) <= set(entries), "trial patches missing from AI index"
    files = {}
    for source_id, entry in entries.items():
        path = AI_DIR / entry["file"]
        assert path.is_file(), f"missing AI patch file: {path}"
        files[source_id] = _load(path)
    return files


def test_ai_index_and_files():
    files = _ai_files()
    index = _load(AI_DIR / "index.json")
    by_source = {e["source_patch_id"]: e for e in index["translations"]}
    for source_id, date in REQUIRED.items():
        entry = by_source[source_id]
        assert entry["date"] == date
        assert entry["ai_patch_id"] == f"ai-{date}-1"
        assert entry["file"].startswith("zh/")
        assert entry["title"].startswith("《守望先锋》补丁说明——")
        assert source_id in files


def test_ai_patches_mirror_sources_and_are_localized():
    files = _ai_files()
    for source_id, out in files.items():
        src = _load(_source_id(source_id))
        _compare_patch(src, out)


def test_ai_translations_do_not_leak_into_official_indexes():
    index = _load(DATA / "patches_index.json")
    assert not any(str(p.get("id", "")).startswith("ai-") for p in index.get("patches", []))
    entries = _load(DATA / "entries_index.json").get("entries", [])
    assert not any("ai-" in str(e.get("patch", "")) for e in entries)
    for hero_file in sorted((DATA / "heroes").glob("*.json")):
        hero = _load(hero_file)
        assert not any("ai-" in str(rec.get("patch", "")) for rec in hero.get("timeline", []))


def test_pages_workflow_stages_ai_translations():
    text = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "data/ai_translations" in text
