"""AI translation of English patches that have no official Chinese counterpart.

The official pipeline never sees this data: it lives under
``data/ai_translations/`` and is only read by the site's ``?lang=ai`` overlay.

Two layers:

- pure helpers (discovery, flatten/rebuild, validation, index) are unit-tested;
- the CLI in ``tools/ai_translate.py`` calls an OpenAI-compatible endpoint,
  reusing the saved owpatch-tool credentials when ``OWPATCH_API_KEY`` is absent.

Credentials are never printed or stored. The default lookup mirrors owpatch-tool:
``OWPATCH_API_KEY`` > ``--translate-config`` > ``<data_dir>/ui-config.toml`` >
``../owpatch-tool/config.toml``.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import json
import os
import pathlib
import re
import sys
import threading
import time
import tomllib
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import requests

AI_DIRNAME = "ai_translations"
SKILL_DIRNAME = "skill"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BATCH_CHARS = 6000
MAX_TOKENS = 8192
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?|\.\d+")
PLACEHOLDERS = ("[待补充]", "TODO", "（译注）", "(译注)")
EN_ONLY_OK = {"AI", "A.I.", "UI", "PC", "PS4 Pro", "Console", "4K", "Boop", "PvP HUD"}
LONG_EN_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9'’.:-]*(?:\s+[A-Za-z][A-Za-z0-9'’.:-]*){6,}"
)
TERM_CATEGORIES = ("heroes", "abilities", "maps", "game_terms")
ROLE_CN = {"tank": "重装", "damage": "输出", "support": "支援"}

_print_lock = threading.Lock()


def _log(message: str) -> None:
    with _print_lock:
        print(message, flush=True)


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def _toml_translate(path: pathlib.Path) -> dict[str, str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {}
    block = data.get("translate")
    if not isinstance(block, dict):
        return {}
    out = {}
    for key in ("api_key", "base_url", "model"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


def _default_data_dir() -> pathlib.Path:
    env = os.environ.get("OWPATCH_DATA_DIR", "").strip()
    if env:
        return pathlib.Path(env).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return pathlib.Path(base) / "owpatch-tool"
        return pathlib.Path.home() / "AppData" / "Local" / "owpatch-tool"
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    base = pathlib.Path(xdg).expanduser() if xdg else pathlib.Path.home() / ".local" / "share"
    return base / "owpatch-tool"


@dataclass
class ApiSettings:
    api_key: str
    base_url: str
    model: str
    source: str

    def public(self) -> dict[str, Any]:
        return {
            "api_key_set": bool(self.api_key),
            "api_key_source": self.source,
            "base_url": self.base_url,
            "model": self.model,
        }


def load_api_settings(
    *,
    translate_config: str | None = None,
    model_override: str | None = None,
) -> ApiSettings:
    """Resolve credentials with owpatch-tool's precedence (no key is logged)."""
    merged: dict[str, str] = {}
    source = ""

    candidates: list[tuple[str, pathlib.Path]] = []
    if translate_config:
        candidates.append(("translate-config", pathlib.Path(translate_config).expanduser()))
    candidates.append(("ui-config.toml", _default_data_dir() / "ui-config.toml"))
    candidates.append(("owpatch-tool/config.toml", pathlib.Path(__file__).resolve().parents[3] / "owpatch-tool" / "config.toml"))

    for label, path in candidates:
        values = _toml_translate(path)
        if not values:
            continue
        if not merged:
            source = label
        for key, value in values.items():
            merged.setdefault(key, value)

    env_key = os.environ.get("OWPATCH_API_KEY", "").strip()
    env_base = os.environ.get("OWPATCH_API_BASE", "").strip()
    env_model = os.environ.get("OWPATCH_API_MODEL", "").strip()
    if env_key:
        merged["api_key"] = env_key
        source = "environment"
    if env_base:
        merged["base_url"] = env_base
    if env_model:
        merged["model"] = env_model
    if model_override:
        merged["model"] = model_override

    return ApiSettings(
        api_key=merged.get("api_key", ""),
        base_url=merged.get("base_url", DEFAULT_BASE_URL),
        model=merged.get("model", DEFAULT_MODEL),
        source=source,
    )


# ---------------------------------------------------------------------------
# Discovery / paths
# ---------------------------------------------------------------------------


@dataclass
class PatchRef:
    source_id: str
    date: str
    title: str
    source_path: pathlib.Path
    chars: int


def _load_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _ai_dir(data_dir: pathlib.Path) -> pathlib.Path:
    return data_dir / AI_DIRNAME


def _ai_file(data_dir: pathlib.Path, source_id: str) -> pathlib.Path:
    match = re.fullmatch(r"en-(\d{4})-(\d{2})-(\d{2})-(\d+)", source_id)
    if not match:
        raise ValueError(f"不支持的源补丁 ID: {source_id}")
    return _ai_dir(data_dir) / "zh" / match.group(1) / f"{match.group(1)}-{match.group(2)}-{match.group(3)}-{match.group(4)}.json"


def _source_file(data_dir: pathlib.Path, source_id: str) -> pathlib.Path:
    match = re.fullmatch(r"en-(\d{4}-\d{2}-\d{2})-(\d+)", source_id)
    if not match:
        raise ValueError(f"不支持的源补丁 ID: {source_id}")
    return data_dir / "patches" / "en" / f"{match.group(1)}-{match.group(2)}.json"


def load_index(data_dir: pathlib.Path) -> dict:
    path = _ai_dir(data_dir) / "index.json"
    if not path.exists():
        return {"schema_version": 1, "updated": "", "notice": "AI 机器翻译，非官方中文；内容与数值以英文原文为准。", "translations": []}
    return _load_json(path)


def existing_by_source(data_dir: pathlib.Path) -> dict[str, dict]:
    return {
        entry["source_patch_id"]: entry
        for entry in load_index(data_dir).get("translations", [])
        if entry.get("source_patch_id")
    }


def missing_patches(
    data_dir: pathlib.Path,
    *,
    year: str | None = None,
    years: Iterable[str] | None = None,
    ids: Iterable[str] | None = None,
    since_days: int | None = None,
    order: str = "oldest",
    force: bool = False,
) -> list[PatchRef]:
    index = _load_json(data_dir / "patches_index.json")
    wanted = set(ids or [])
    wanted_years = set(years or ())
    known = existing_by_source(data_dir)
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=since_days)) if since_days else None
    out: list[PatchRef] = []
    for patch in index.get("patches", []):
        if patch.get("patch_id_cn"):
            continue
        source_id = patch.get("patch_id_en") or ""
        if not source_id.startswith("en-"):
            continue
        if wanted and source_id not in wanted:
            continue
        if year and not patch.get("date", "").startswith(year):
            continue
        if wanted_years and patch.get("date", "")[:4] not in wanted_years:
            continue
        if cutoff and patch.get("date", "") < cutoff.isoformat():
            continue
        source_path = _source_file(data_dir, source_id)
        if not source_path.exists():
            continue
        ai_path = _ai_file(data_dir, source_id)
        if ai_path.exists() and not force:
            try:
                ai = _load_json(ai_path)
            except ValueError:
                ai = {}
            if ai.get("translation", {}).get("source_hash") == _load_json(source_path).get("hash"):
                continue
        out.append(PatchRef(
            source_id=source_id,
            date=patch.get("date", ""),
            title=patch.get("title_en") or source_id,
            source_path=source_path,
            chars=patch.get("chars_en") or 0,
        ))
    out.sort(key=lambda p: (p.date, p.source_id), reverse=(order == "newest"))
    return out


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


@dataclass
class Unit:
    unit_id: str
    kind: str
    context: str
    text: str


def _add(units: list[Unit], unit_id: str, kind: str, context: str, text: Any) -> None:
    if isinstance(text, str) and text.strip():
        units.append(Unit(unit_id, kind, context, text))


def flatten_patch(patch: dict) -> list[Unit]:
    units: list[Unit] = []
    for si, section in enumerate(patch.get("sections") or []):
        sec_ctx = section.get("title") or ""
        _add(units, f"s{si}.title", "section_title", sec_ctx, section.get("title"))
        _add(units, f"s{si}.description", "section_description", sec_ctx, section.get("description"))
        _add(units, f"s{si}.dev", "section_dev", sec_ctx, section.get("dev"))
        for hi, hero in enumerate(section.get("heroes") or []):
            hero_name = hero.get("name_en") or hero.get("name_cn") or hero.get("slug") or ""
            hero_ctx = f"{sec_ctx} / {hero_name}".strip(" /")
            if not hero.get("name_cn"):
                _add(units, f"s{si}.h{hi}.name_cn", "hero_name", hero_ctx, hero.get("name_en"))
            _add(units, f"s{si}.h{hi}.dev_note", "hero_dev", hero_ctx, hero.get("dev_note"))
            for gi, entry in enumerate(hero.get("general") or []):
                if isinstance(entry, dict):
                    if not entry.get("text_cn"):
                        _add(units, f"s{si}.h{hi}.general.{gi}", "general", hero_ctx, entry.get("text_en"))
                else:
                    _add(units, f"s{si}.h{hi}.general.{gi}", "general", hero_ctx, entry)
            for pi, perk in enumerate(hero.get("perks") or []):
                p_ctx = f"{hero_ctx} / {perk.get('name_en') or ''}".strip(" /")
                if not perk.get("name_cn"):
                    _add(units, f"s{si}.h{hi}.perk.{pi}.name_cn", "perk_name", p_ctx, perk.get("name_en"))
                for li, line in enumerate(perk.get("lines_en") or []):
                    _add(units, f"s{si}.h{hi}.perk.{pi}.lines.{li}", "perk_line", p_ctx, line)
            for ai, ability in enumerate(hero.get("abilities") or []):
                a_ctx = f"{hero_ctx} / {ability.get('name_en') or ''}".strip(" /")
                if not ability.get("name_cn"):
                    _add(units, f"s{si}.h{hi}.a{ai}.name_cn", "ability_name", a_ctx, ability.get("name_en"))
                for ci, change in enumerate(ability.get("changes") or []):
                    _add(units, f"s{si}.h{hi}.a{ai}.changes.{ci}", "change", a_ctx, change.get("text_en"))
            for ii, item in enumerate(hero.get("stadium_items") or []):
                i_ctx = f"{hero_ctx} / {item.get('name_en') or ''}".strip(" /")
                if not item.get("name_cn"):
                    _add(units, f"s{si}.h{hi}.item.{ii}.name_cn", "item_name", i_ctx, item.get("name_en"))
                for li, line in enumerate(item.get("lines_en") or []):
                    _add(units, f"s{si}.h{hi}.item.{ii}.lines.{li}", "item_line", i_ctx, line)
        for bi, block in enumerate(section.get("blocks") or []):
            b_ctx = f"{sec_ctx} / {block.get('title') or ''}".strip(" /")
            _add(units, f"s{si}.b{bi}.title", "block_title", b_ctx, block.get("title"))
            _add(units, f"s{si}.b{bi}.body", "block_body", b_ctx, block.get("body"))
            _add(units, f"s{si}.b{bi}.dev", "block_dev", b_ctx, block.get("dev"))
        for mi, map_update in enumerate(section.get("maps") or []):
            m_ctx = f"{sec_ctx} / {map_update.get('map_name') or ''}".strip(" /")
            _add(units, f"s{si}.m{mi}.map_name", "map_name", m_ctx, map_update.get("map_name"))
            _add(units, f"s{si}.m{mi}.area", "map_area", m_ctx, map_update.get("area"))
    return units


def make_batches(units: list[Unit], max_chars: int = DEFAULT_BATCH_CHARS) -> list[list[Unit]]:
    batches: list[list[Unit]] = []
    current: list[Unit] = []
    size = 0
    for unit in units:
        length = len(unit.text)
        if current and size + length > max_chars:
            batches.append(current)
            current = []
            size = 0
        current.append(unit)
        size += length
    if current:
        batches.append(current)
    return batches


# ---------------------------------------------------------------------------
# Prompt / terms
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def load_skill(data_dir: pathlib.Path) -> tuple[str, dict]:
    skill = _ai_dir(data_dir) / SKILL_DIRNAME
    prompt = (skill / "system_prompt.md").read_text(encoding="utf-8")
    terms = _load_json(skill / "overwatch_terms.json")
    return prompt, terms


def build_system_prompt(raw_prompt: str) -> str:
    rules = raw_prompt
    marker = "## 输出契约"
    if marker in rules:
        rules = rules.split(marker, 1)[0]
    return rules.rstrip() + """

## JSON 输出契约

你会收到一个 JSON 数组，元素为 `{"id": "...", "kind": "...", "context": "...", "text": "..."}`。
请把每个 `text` 完整翻译成简体中文，只输出一个 JSON 对象：键与输入 `id` 完全一致，值为中文译文。
不要输出代码围栏、解释、原文、编号或任何额外字段。每个值只放译文本身。
"""


def _term_index(terms: dict) -> list[tuple[str, str, re.Pattern]]:
    index = []
    for category in TERM_CATEGORIES:
        for english, chinese in (terms.get("terms", {}).get(category) or {}).items():
            if not isinstance(english, str) or not isinstance(chinese, str) or not chinese.strip():
                continue
            needle = _normalize(english).strip()
            if not needle:
                continue
            pattern = re.compile(rf"(?<![a-z0-9]){re.escape(needle)}(?:s|es)?(?![a-z0-9])")
            index.append((english, chinese, pattern))
    return index


def select_terms(terms: dict, text: str, limit: int = 260) -> list[tuple[str, str]]:
    normalized = _normalize(text)
    picked: list[tuple[str, str]] = []
    seen = set()
    core = terms.get("core_terms") or []
    for category in TERM_CATEGORIES:
        for english, chinese in (terms.get("terms", {}).get(category) or {}).items():
            if english in core and english not in seen:
                picked.append((english, chinese))
                seen.add(english)
    for english, chinese, pattern in _term_index(terms):
        if english in seen:
            continue
        if pattern.search(normalized):
            picked.append((english, chinese))
            seen.add(english)
            if len(picked) >= limit:
                break
    return picked[:limit]


def build_user_prompt(batch: list[Unit], term_pairs: list[tuple[str, str]]) -> str:
    lines = ["# 术语对照（优先使用）"]
    if term_pairs:
        lines += [f"- {en} => {zh}" for en, zh in term_pairs]
    else:
        lines.append("- （本批无命中术语）")
    lines += ["", "# 待翻译条目（只输出 JSON 对象）"]
    payload = [
        {"id": unit.unit_id, "kind": unit.kind, "context": unit.context, "text": unit.text}
        for unit in batch
    ]
    lines.append(json.dumps(payload, ensure_ascii=False))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------


class TranslateError(RuntimeError):
    pass


class ApiClient:
    def __init__(self, settings: ApiSettings, timeout: float = 180.0):
        self.settings = settings
        self.timeout = timeout
        self.calls = 0
        self.usage: Counter = Counter()
        base = settings.base_url.rstrip("/")
        self.endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self.settings.api_key:
            raise TranslateError("未配置 API key")
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": MAX_TOKENS,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        last: Exception | None = None
        for attempt in range(1, 7):
            try:
                response = requests.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout)
                self.calls += 1
                if response.status_code in (401, 403):
                    raise TranslateError(f"鉴权失败 HTTP {response.status_code}；请检查 key/base_url")
                if response.status_code == 404:
                    raise TranslateError(f"接口不存在 HTTP 404：{self.endpoint}")
                if response.status_code == 429 or response.status_code >= 500:
                    raise _Retry(f"HTTP {response.status_code}: {response.text[:200]}")
                if not response.ok:
                    raise TranslateError(f"HTTP {response.status_code}: {response.text[:300]}")
                data = response.json()
                usage = data.get("usage") or {}
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    if isinstance(usage.get(key), int):
                        self.usage[key] += usage[key]
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise _Retry("模型返回空内容")
                return content
            except TranslateError:
                raise
            except (_Retry, requests.Timeout, requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
                last = exc
                if attempt < 6:
                    time.sleep(min(20.0, 1.5 ** attempt))
        raise TranslateError(f"请求重试 6 次仍失败: {last}")


class _Retry(Exception):
    pass


def parse_translation_json(content: str) -> dict[str, str]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    decoder = json.JSONDecoder()
    out: dict[str, str] = {}
    pos = 0
    found = 0
    while True:
        start = text.find("{", pos)
        if start < 0:
            break
        try:
            data, end = decoder.raw_decode(text, start)
        except ValueError:
            pos = start + 1
            continue
        found += 1
        pos = end
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if isinstance(value, str) and value.strip():
                out[str(key)] = value.strip()
    if not found:
        raise TranslateError("模型没有返回 JSON 对象")
    if not out:
        raise TranslateError("模型返回的 JSON 没有可用译文")
    return out


def translate_batch(
    client: ApiClient,
    batch: list[Unit],
    terms: dict,
    system_prompt: str,
) -> dict[str, str]:
    ids = {unit.unit_id for unit in batch}
    text = "\n".join(unit.text for unit in batch)
    term_pairs = select_terms(terms, text)
    for attempt in range(3):
        user_prompt = build_user_prompt(batch, term_pairs)
        if attempt:
            missing = sorted(ids - set(translations))
            user_prompt += (
                f"\n\n上一次返回缺少这些 id，请补齐并只输出完整 JSON：{json.dumps(missing, ensure_ascii=False)}"
            )
        content = client.chat(system_prompt, user_prompt)
        translations = parse_translation_json(content)
        if ids <= set(translations):
            return {unit_id: translations[unit_id] for unit_id in ids}
    missing = sorted(ids - set(translations))
    raise TranslateError(f"批次缺少 {len(missing)} 个译文（示例 {missing[:5]}）")


def translate_batch_safe(
    client: ApiClient,
    batch: list[Unit],
    terms: dict,
    system_prompt: str,
    depth: int = 0,
) -> dict[str, str]:
    """Retry a failed batch, then split it in half so one bad item cannot sink
    the whole patch (models occasionally drop the tail of a long JSON object)."""
    try:
        return translate_batch(client, batch, terms, system_prompt)
    except TranslateError:
        if len(batch) <= 1 or depth >= 3:
            raise
        mid = len(batch) // 2
        out = translate_batch_safe(client, batch[:mid], terms, system_prompt, depth + 1)
        out.update(translate_batch_safe(client, batch[mid:], terms, system_prompt, depth + 1))
        return out


# ---------------------------------------------------------------------------
# Rebuild / validation
# ---------------------------------------------------------------------------


def _title_for(date_text: str) -> str:
    year, month, day = date_text.split("-")
    return f"《守望先锋》补丁说明——{int(year)}年{int(month)}月{int(day)}日"


def build_ai_patch(source: dict, translations: dict[str, str], *, model: str, provider: str) -> dict:
    out = copy.deepcopy(source)
    out["id"] = f"ai-{source['date']}-{source.get('seq', 1)}"
    out["site"] = "ai"
    out["title"] = _title_for(source["date"])
    out["hash"] = None
    out["source_patch_id"] = source.get("id")
    for section in out.get("sections") or []:
        for hero in section.get("heroes") or []:
            for collection in ("perks", "stadium_items"):
                for item in hero.get(collection) or []:
                    item["lines_cn"] = [""] * len(item.get("lines_en") or [])
    kept: list[str] = []

    def put(unit_id: str, value: str) -> None:
        parts = unit_id.split(".")
        if parts[0].startswith("s"):
            si = int(parts[0][1:])
            section = out["sections"][si]
            if len(parts) == 2:
                if parts[1] == "description":
                    section["description"] = value
                elif parts[1] == "dev":
                    section["dev"] = value
                else:
                    section["title"] = value
                return
            if len(parts) == 3 and parts[1].startswith("b"):
                bi = int(parts[1][1:])
                section["blocks"][bi][parts[2]] = value
                return
            if len(parts) == 3 and parts[1].startswith("m"):
                mi = int(parts[1][1:])
                section["maps"][mi][parts[2]] = value
                return
            if not parts[1].startswith("h"):
                raise ValueError(f"无法应用译文单元: {unit_id}")
            hi = int(parts[1][1:])
            hero = section["heroes"][hi]
            if len(parts) == 3 and parts[2] == "name_cn":
                hero["name_cn"] = value
                return
            if len(parts) == 3 and parts[2] == "dev_note":
                hero["dev_note"] = value
                return
            if len(parts) == 4 and parts[2] == "general":
                gi = int(parts[3])
                entry = hero["general"][gi]
                if isinstance(entry, dict):
                    entry["text_cn"] = value
                    entry["text_en"] = None
                else:
                    hero["general"][gi] = value
                return
            if len(parts) == 5 and parts[2] == "perk":
                pi = int(parts[3])
                perk = hero["perks"][pi]
                if parts[4] == "name_cn":
                    perk["name_cn"] = value
                return
            if len(parts) == 6 and parts[2] == "perk" and parts[4] == "lines":
                pi = int(parts[3])
                li = int(parts[5])
                hero["perks"][pi]["lines_cn"][li] = value
                return
            if len(parts) == 4 and parts[2].startswith("a") and parts[3] == "name_cn":
                ai = int(parts[2][1:])
                hero["abilities"][ai]["name_cn"] = value
                return
            if len(parts) == 5 and parts[2].startswith("a") and parts[3] == "changes":
                ai = int(parts[2][1:])
                ci = int(parts[4])
                change = hero["abilities"][ai]["changes"][ci]
                change["text_cn"] = value
                change["text_en"] = None
                return
            if len(parts) == 5 and parts[2] == "item":
                ii = int(parts[3])
                if parts[4] == "name_cn":
                    hero["stadium_items"][ii]["name_cn"] = value
                return
            if len(parts) == 6 and parts[2] == "item" and parts[4] == "lines":
                ii = int(parts[3])
                li = int(parts[5])
                hero["stadium_items"][ii]["lines_cn"][li] = value
                return
            if len(parts) == 3 and parts[1].startswith("b"):
                bi = int(parts[1][1:])
                block = section["blocks"][bi]
                block[parts[2]] = value
                return
            if len(parts) == 3 and parts[1].startswith("m"):
                mi = int(parts[1][1:])
                section["maps"][mi][parts[2]] = value
                return
        raise ValueError(f"无法应用译文单元: {unit_id}")

    for unit_id, value in translations.items():
        put(unit_id, value)

    # Ensure every translated line list has the right length.
    for section in out.get("sections") or []:
        for hero in section.get("heroes") or []:
            for collection, target in (("perks", "lines_cn"), ("stadium_items", "lines_cn")):
                for item in hero.get(collection) or []:
                    source_lines = item.get("lines_en") or []
                    lines = item.setdefault(target, [])
                    while len(lines) < len(source_lines):
                        lines.append("")
    source_texts = {unit.unit_id: unit.text for unit in flatten_patch(source)}
    for unit_id, value in translations.items():
        original = source_texts.get(unit_id, "")
        if original and value.strip() == original.strip() and re.search(r"[A-Za-z]", value):
            kept.append(value.strip())
    out["translation"] = {
        "skill": "overwatch-patch-translation v7.6",
        "engine": provider,
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "draft",
        "source_hash": source.get("hash"),
        "kept_english": sorted(set(kept))[:50],
    }
    return out


def _numbers(text: str) -> Counter:
    tokens = [(t if not t.startswith(".") else "0" + t) for t in NUMBER_RE.findall(text)]
    return Counter(tokens)


def _bullet_shape(text: str) -> list[int]:
    return [len(line) - len(line.lstrip(" ")) for line in text.splitlines() if line.lstrip().startswith("- ")]


def _check_text(
    source: str,
    target: str,
    where: str,
    errors: list[str],
    *,
    strict_numbers: bool = False,
    allow_english_equal: bool = False,
    allow_english: bool = False,
) -> None:
    if not source:
        return
    same_english = allow_english_equal and target.strip() == source.strip()
    if not allow_english and not same_english and (not target or (not CJK_RE.search(target) and target.strip() not in EN_ONLY_OK)):
        errors.append(f"{where}: 目标不是中文或为空")
    if strict_numbers and _numbers(source) != _numbers(target):
        errors.append(f"{where}: 数字 token 变化 {_numbers(source)} -> {_numbers(target)}")
    if _bullet_shape(source) != _bullet_shape(target):
        errors.append(f"{where}: 列表结构变化")
    for marker in PLACEHOLDERS:
        if marker in target:
            errors.append(f"{where}: 含占位符 {marker}")
    long_en = LONG_EN_RE.search(target)
    if long_en and not allow_english:
        errors.append(f"{where}: 疑似未翻译英文 {long_en.group(0)[:60]!r}")


def validate_ai_patch(source: dict, out: dict) -> list[str]:
    errors: list[str] = []
    if out.get("site") != "ai":
        errors.append("site 不是 ai")
    if out.get("id") != f"ai-{source['date']}-{source.get('seq', 1)}":
        errors.append("id 不匹配")
    if out.get("source_patch_id") != source.get("id"):
        errors.append("source_patch_id 不匹配")
    if out.get("date") != source.get("date") or out.get("seq") != source.get("seq"):
        errors.append("date/seq 不匹配")
    if out.get("title") != _title_for(source["date"]):
        errors.append("title 不匹配")
    if out.get("translation", {}).get("source_hash") != source.get("hash"):
        errors.append("source_hash 不匹配")
    sections = source.get("sections") or []
    out_sections = out.get("sections") or []
    if len(sections) != len(out_sections):
        errors.append("section 数量不一致")
        return errors
    for si, (a, b) in enumerate(zip(sections, out_sections)):
        sw = f"s{si}"
        if a.get("type") != b.get("type") or a.get("role") != b.get("role"):
            errors.append(f"{sw}: type/role 变化")
        _check_text(a.get("title") or "", b.get("title") or "", f"{sw}.title", errors, allow_english_equal=True)
        _check_text(a.get("description") or "", b.get("description") or "", f"{sw}.description", errors)
        _check_text(a.get("dev") or "", b.get("dev") or "", f"{sw}.dev", errors)
        heroes = a.get("heroes") or []
        if len(heroes) != len(b.get("heroes") or []):
            errors.append(f"{sw}: hero 数量不一致")
            continue
        for hi, (h, ho) in enumerate(zip(heroes, b["heroes"])):
            hw = f"{sw}.h{hi}"
            for key in ("slug", "name_en", "role", "icon"):
                if h.get(key) != ho.get(key):
                    errors.append(f"{hw}: {key} 变化")
            if not ho.get("name_cn"):
                errors.append(f"{hw}: name_cn 空")
            if h.get("name_cn") and h.get("name_cn") != ho.get("name_cn"):
                errors.append(f"{hw}: 已有 name_cn 被改")
            _check_text(h.get("dev_note") or "", ho.get("dev_note") or "", f"{hw}.dev_note", errors)
            general = h.get("general") or []
            if len(general) != len(ho.get("general") or []):
                errors.append(f"{hw}: general 数量不一致")
            else:
                for gi, (g, go) in enumerate(zip(general, ho["general"])):
                    gs = g if isinstance(g, str) else (g.get("text_en") or "")
                    gt = go if isinstance(go, str) else (go.get("text_cn") or "")
                    strict = isinstance(g, dict) and any(
                        g.get(key) is not None for key in ("before", "after", "by", "by_pct")
                    )
                    _check_text(gs, gt, f"{hw}.general.{gi}", errors, strict_numbers=strict)
                    if isinstance(g, dict):
                        if isinstance(go, dict):
                            for key in ("before", "after", "by", "by_pct", "metric", "raw_metric", "unit", "dimension", "subject"):
                                if g.get(key) != go.get(key):
                                    errors.append(f"{hw}.general.{gi}: {key} 变化")
                            if go.get("text_en") is not None:
                                errors.append(f"{hw}.general.{gi}: text_en 未置空")
            for pi, (p, po) in enumerate(zip(h.get("perks") or [], ho.get("perks") or [])):
                if p.get("name_en") != po.get("name_en") or p.get("status") != po.get("status"):
                    errors.append(f"{hw}.perk.{pi}: 元数据变化")
                if not po.get("name_cn"):
                    errors.append(f"{hw}.perk.{pi}: name_cn 空")
                for li, (line, out_line) in enumerate(zip(p.get("lines_en") or [], po.get("lines_cn") or [])):
                    _check_text(line, out_line, f"{hw}.perk.{pi}.lines.{li}", errors)
            abilities = h.get("abilities") or []
            if len(abilities) != len(ho.get("abilities") or []):
                errors.append(f"{hw}: ability 数量不一致")
                continue
            for ai, (ability, ao) in enumerate(zip(abilities, ho["abilities"])):
                aw = f"{hw}.a{ai}"
                for key in ("slug", "name_en", "icon"):
                    if ability.get(key) != ao.get(key):
                        errors.append(f"{aw}: {key} 变化")
                if not ao.get("name_cn") and (ability.get("name_en") or ability.get("name_cn") or ability.get("slug")):
                    errors.append(f"{aw}: name_cn 空")
                changes = ability.get("changes") or []
                if len(changes) != len(ao.get("changes") or []):
                    errors.append(f"{aw}: change 数量不一致")
                    continue
                for ci, (c, co) in enumerate(zip(changes, ao["changes"])):
                    cw = f"{aw}.changes.{ci}"
                    for key in ("before", "after", "by", "by_pct", "metric", "raw_metric", "unit"):
                        if c.get(key) != co.get(key):
                            errors.append(f"{cw}: {key} 变化")
                    if co.get("text_en") is not None:
                        errors.append(f"{cw}: text_en 未置空")
                    strict = any(c.get(key) is not None for key in ("before", "after", "by", "by_pct"))
                    _check_text(c.get("text_en") or "", co.get("text_cn") or "", cw, errors, strict_numbers=strict)
            for ii, (item, io) in enumerate(zip(h.get("stadium_items") or [], ho.get("stadium_items") or [])):
                if item.get("status") != io.get("status") or item.get("kind") != io.get("kind") or item.get("rarity") != io.get("rarity"):
                    errors.append(f"{hw}.item.{ii}: 元数据变化")
                if not io.get("name_cn"):
                    errors.append(f"{hw}.item.{ii}: name_cn 空")
                for li, (line, out_line) in enumerate(zip(item.get("lines_en") or [], io.get("lines_cn") or [])):
                    _check_text(line, out_line, f"{hw}.item.{ii}.lines.{li}", errors)
        blocks = a.get("blocks") or []
        if len(blocks) != len(b.get("blocks") or []):
            errors.append(f"{sw}: block 数量不一致")
        else:
            for bi, (bl, bo) in enumerate(zip(blocks, b["blocks"])):
                _check_text(bl.get("title") or "", bo.get("title") or "", f"{sw}.b{bi}.title", errors, allow_english_equal=True)
                _check_text(bl.get("body") or "", bo.get("body") or "", f"{sw}.b{bi}.body", errors, allow_english=True)
                _check_text(bl.get("dev") or "", bo.get("dev") or "", f"{sw}.b{bi}.dev", errors)
        maps = a.get("maps") or []
        if len(maps) != len(b.get("maps") or []):
            errors.append(f"{sw}: map 数量不一致")
        else:
            for mi, (m, mo) in enumerate(zip(maps, b["maps"])):
                _check_text(m.get("map_name") or "", mo.get("map_name") or "", f"{sw}.m{mi}.map_name", errors)
                _check_text(m.get("area") or "", mo.get("area") or "", f"{sw}.m{mi}.area", errors)
    return errors


# ---------------------------------------------------------------------------
# Index / status
# ---------------------------------------------------------------------------


def rebuild_index(data_dir: pathlib.Path) -> dict:
    ai_dir = _ai_dir(data_dir)
    entries = []
    for path in sorted(ai_dir.glob("zh/**/*.json")):
        try:
            data = _load_json(path)
        except ValueError:
            continue
        if data.get("site") != "ai" or not data.get("source_patch_id"):
            continue
        entries.append({
            "source_patch_id": data["source_patch_id"],
            "ai_patch_id": data.get("id"),
            "date": data.get("date", ""),
            "title": data.get("title", ""),
            "file": path.relative_to(ai_dir).as_posix(),
            "status": (data.get("translation") or {}).get("status", "draft"),
        })
    entries.sort(key=lambda e: (e["date"], e["source_patch_id"]))
    index = {
        "schema_version": 1,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notice": "AI 机器翻译，非官方中文；内容与数值以英文原文为准。",
        "translations": entries,
    }
    (ai_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return index


def status(data_dir: pathlib.Path, *, year: str | None = None) -> dict:
    missing = missing_patches(data_dir, year=year)
    index = load_index(data_dir)
    settings = load_api_settings()
    return {
        "missing": len(missing),
        "done": len(index.get("translations", [])),
        "chars": sum(p.chars for p in missing),
        "years": sorted({p.date[:4] for p in missing}),
        "api": settings.public(),
    }


def validate_all(data_dir: pathlib.Path) -> list[str]:
    errors: list[str] = []
    for entry in load_index(data_dir).get("translations", []):
        source_id = entry.get("source_patch_id")
        try:
            source = _load_json(_source_file(data_dir, source_id))
            out = _load_json(_ai_dir(data_dir) / entry["file"])
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f"{source_id}: 无法读取 {exc}")
            continue
        for error in validate_ai_patch(source, out):
            errors.append(f"{source_id}: {error}")
    return errors


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _translate_one(data_dir: pathlib.Path, client: ApiClient, ref: PatchRef, *, batch_chars: int, system_prompt: str, terms: dict) -> None:
    source = _load_json(ref.source_path)
    units = flatten_patch(source)
    if not units:
        raise TranslateError("没有可翻译字段（可能是 raw_text 补丁）")
    translations: dict[str, str] = {}
    for batch in make_batches(units, batch_chars):
        translations.update(translate_batch_safe(client, batch, terms, system_prompt))
    out = build_ai_patch(source, translations, model=client.settings.model, provider="api")
    errors = validate_ai_patch(source, out)
    if errors:
        raise TranslateError("校验失败: " + "; ".join(errors[:5]))
    path = _ai_file(data_dir, ref.source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run(
    data_dir: pathlib.Path,
    *,
    ids: list[str] | None = None,
    year: str | None = None,
    years: list[str] | None = None,
    limit: int = 0,
    order: str = "oldest",
    since_days: int | None = None,
    concurrency: int = 3,
    batch_chars: int = DEFAULT_BATCH_CHARS,
    force: bool = False,
    dry_run: bool = False,
    translate_config: str | None = None,
    model_override: str | None = None,
) -> int:
    settings = load_api_settings(translate_config=translate_config, model_override=model_override)
    refs = missing_patches(data_dir, year=year, years=years, ids=ids, since_days=since_days, order=order, force=force)
    if limit:
        refs = refs[:limit]
    _log(f"待翻译 {len(refs)} 篇；API {settings.base_url} 模型 {settings.model}，key 来源 {settings.source or '无'}")
    if not refs:
        _log("没有需要翻译的补丁")
        if not (_ai_dir(data_dir) / "index.json").exists():
            rebuild_index(data_dir)
        return 0
    if dry_run:
        total_units = 0
        for ref in refs:
            units = flatten_patch(_load_json(ref.source_path))
            total_units += len(units)
            _log(f"[dry-run] {ref.source_id} {len(units)} 条 / {len(make_batches(units, batch_chars))} 批")
        _log(f"[dry-run] 合计 {total_units} 条")
        return 0
    if not settings.api_key:
        _log("缺少 OWPATCH_API_KEY：可用环境变量、--translate-config 或 owpatch-tool 的 ui-config.toml")
        return 2
    prompt, terms = load_skill(data_dir)
    system_prompt = build_system_prompt(prompt)
    client = ApiClient(settings)
    failures: list[tuple[str, str]] = []
    start = time.time()

    def worker(ref: PatchRef) -> tuple[str, str | None]:
        try:
            _translate_one(data_dir, client, ref, batch_chars=batch_chars, system_prompt=system_prompt, terms=terms)
            _log(f"[OK] {ref.source_id} ({ref.chars} 字符)")
            return ref.source_id, None
        except Exception as exc:  # noqa: BLE001 - per-patch isolation
            _log(f"[FAIL] {ref.source_id}: {exc}")
            return ref.source_id, str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for source_id, error in pool.map(worker, refs):
            if error:
                failures.append((source_id, error))
    index = rebuild_index(data_dir)
    elapsed = time.time() - start
    _log(f"完成：成功 {len(refs) - len(failures)}，失败 {len(failures)}，索引 {len(index['translations'])} 条，用时 {elapsed:.0f}s，API 调用 {client.calls}，usage {dict(client.usage)}")
    if failures:
        for source_id, error in failures[:20]:
            _log(f"  - {source_id}: {error}")
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None, *, data_dir: pathlib.Path | None = None) -> int:
    if data_dir is None:
        # In CI the package is installed into site-packages, so __file__ is not
        # under the checkout. The workflow runs from the repository root.
        candidate = pathlib.Path.cwd() / "data"
        package_candidate = pathlib.Path(__file__).resolve().parents[2] / "data"
        if (candidate / "patches_index.json").exists():
            data_dir = candidate
        elif (package_candidate / "patches_index.json").exists():
            data_dir = package_candidate
        else:
            data_dir = candidate
    data = data_dir
    parser = argparse.ArgumentParser(description="AI 翻译缺少官方中文的补丁")
    sub = parser.add_subparsers(dest="command", required=True)

    status_p = sub.add_parser("status", help="查看缺口和凭据来源")
    status_p.add_argument("--json", action="store_true")
    status_p.add_argument("--year")

    run_p = sub.add_parser("run", help="翻译缺失补丁")
    run_p.add_argument("--missing", action="store_true", help="只翻译缺少官方中文的补丁（默认行为）")
    run_p.add_argument("--ids", nargs="+")
    run_p.add_argument("--year")
    run_p.add_argument("--years", nargs="+")
    run_p.add_argument("--limit", type=int, default=0)
    run_p.add_argument("--order", choices=("oldest", "newest"), default="oldest")
    run_p.add_argument("--since-days", type=int)
    run_p.add_argument("--concurrency", type=int, default=3)
    run_p.add_argument("--batch-chars", type=int, default=DEFAULT_BATCH_CHARS)
    run_p.add_argument("--force", action="store_true")
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--translate-config")
    run_p.add_argument("--model")

    sub.add_parser("validate", help="校验全部 AI 译文")
    sub.add_parser("index", help="从 AI 文件重建索引")

    args = parser.parse_args(argv)
    if args.command == "status":
        info = status(data, year=args.year)
        if args.json:
            print(json.dumps(info, ensure_ascii=False, indent=1))
        else:
            print(f"缺中文官方: {info['missing']} 篇 / {info['chars']} 字符; 已有 AI: {info['done']} 篇")
            print(f"年份: {', '.join(info['years']) or '-'}")
            print(f"API: {info['api']}")
        return 0
    if args.command == "validate":
        errors = validate_all(data)
        for error in errors:
            print(error)
        print(f"校验完成：{len(errors)} 个错误")
        return 1 if errors else 0
    if args.command == "index":
        index = rebuild_index(data)
        print(f"索引已重建：{len(index['translations'])} 条")
        return 0
    if args.command == "run":
        return run(
            data,
            ids=args.ids,
            year=args.year,
            years=args.years,
            limit=args.limit,
            order=args.order,
            since_days=args.since_days,
            concurrency=args.concurrency,
            batch_chars=args.batch_chars,
            force=args.force,
            dry_run=args.dry_run,
            translate_config=args.translate_config,
            model_override=args.model,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
